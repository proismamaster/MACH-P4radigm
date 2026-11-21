"""Offline L5 regressions for the CUP. Run from the repository root."""

import importlib.util
import os
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from city_sdk.city import LEDGER, City, Message, Need, Peer

path = Path(__file__).resolve().parents[1] / "asst/booking_centre/agent/agent.py"
spec = importlib.util.spec_from_file_location("cup_l5", path)
cup = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cup
spec.loader.exec_module(cup)
cup._WAIT_SECONDS = 0.0  # the fake Ledger answers in the next turn: no patient wait

CITIZEN = "citizen:fixture"
AGENT = "agent:fixture/booking_centre"
HOSPITAL = "agent:fixture/hospital"
PARTNER = "agent:partner/hospital"
RX = "prescription_number-FIXTURE"
NOW = "2026-11-23T13:00:00Z"


def slot(identifier, doctor, time, day, *, live=False, extra=""):
    date_field, day_field = ("agenda_date", "agenda_day") if live else ("at", "day")
    return (
        f"slot_id={identifier} doctor_id={doctor} facility={HOSPITAL} procedure=VIS-FIS "
        f"{date_field}=2026-11-{time}:00Z {day_field}={day} {extra}"
    )


class Mailbox:
    def __init__(self, name, priority, *pages, procedure="VIS-FIS"):
        self.need_id = f"N-FIXTURE-{name}"
        self.rows = []
        self.sent = []
        self.add(LEDGER, f"agenda agenda_now={NOW}")
        self.add(LEDGER, f"prescription prescription_number={RX} state=issued procedure={procedure} priority={priority}")
        for page, slots in enumerate(pages, start=1):
            self.add(LEDGER, f"slots page={page}/{len(pages)}\n" + "\n".join(slots))

    def add(self, sender, text, recipient=AGENT):
        row = Message(
            type="chat", sender=sender, recipient=recipient, msg_id=str(len(self.rows)),
            need_id=self.need_id, body={"text": text},
        )
        self.rows.append(row)
        return row

    async def search(self, query):
        return []

    async def history(self, *, peer, need_id):
        return [row for row in self.rows if peer is None or peer in (row.sender, row.recipient)]

    async def post(self, *, to, message_type, body, need_id, conversation_id, traceparent):
        row = self.add(AGENT, body["text"], to)
        self.sent.append(row)
        return row.msg_id

    async def offer(self, criteria):
        inbound = self.add(CITIZEN, f"need.request prescription_number={RX} {criteria}")
        await self.turn(inbound)
        return [option for row in self.sent if row.recipient == CITIZEN for option in cup._offer_blocks(row.text)]

    async def turn(self, inbound):
        city = City(index=self, history=self, messages=self, agent_id=AGENT, inbound=inbound)
        with patch.dict(os.environ, {"CITY_ROLE": "booking_centre"}), patch.object(cup, "_CUP_RING", ()), patch.object(cup, "_PULL_PAUSE", 0):
            await cup.main(Need(message=inbound), city)


class CupLevelFiveTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_need_retry_after_no_slots_rechecks_partners_in_formal_language(self):
        # Arena 1410008 and 2630005: English prose, but different formal doctor languages.
        requests = (
            ("1410008", "hi", "fr, lowkey my back is killing me, can i get a doc who speaks english?"),
            ("2630005", "ka", "Excuse me, I have a referral for back pain and was hoping to schedule an "
                              "appointment with a doctor who speaks English, if possible."),
        )
        for need, language, prose in requests:
            with self.subTest(need=need, language=language):
                mailbox = Mailbox(need, "B", [slot("english", "h1", "24T10:00", "tue")])
                text = (f"{prose} need.request area={{'district':_4}} lang={language} "
                        f"prescription_number={RX} service_type=hospital.physiatry")
                original = mailbox.add(CITIZEN, text)
                mailbox.add(AGENT, f"need.request service_type=hospital.physiatry procedure=VIS-FIS priority=B "
                                   f"request_id=rq-old lang={language}", PARTNER)
                mailbox.add(PARTNER, "cancel reason=no_availability request_id=rq-old")
                mailbox.add(AGENT, cup._no_slots_text("", "no_slots"), CITIZEN)

                candidates = [Peer(PARTNER, role="hospital", capabilities=("hospital.physiatry",))]
                with patch.object(mailbox, "search", return_value=candidates) as find:
                    await mailbox.turn(original)
                    find.assert_not_awaited()
                    await mailbox.turn(mailbox.add(CITIZEN, text))
                    find.assert_awaited_once()
                    (search,) = [row for row in mailbox.sent if row.recipient == PARTNER]
                    fields = cup.fields_of(search.text)
                    self.assertEqual(fields["lang"], language)
                    self.assertNotEqual(fields["request_id"], "rq-old")
                    self.assertNotIn(CITIZEN, search.text)
                    self.assertNotIn(RX, search.text)

                    # Another replay, even after cache eviction, must not start a third round.
                    cup._SENT.pop(mailbox.need_id, None)
                    await mailbox.turn(mailbox.add(CITIZEN, text))
                    find.assert_awaited_once()

                remote = (f"offer offer_id=of-{{slot}} slot_id={{slot}} doctor_id=foreign-h3 facility={PARTNER} "
                          "procedure=VIS-FIS agenda_date=2026-11-24T10:00:00Z agenda_day=tue "
                          "doctor_lang=it/{language} request_id={request}")
                await mailbox.turn(mailbox.add(PARTNER, remote.format(slot="late", language=language, request="rq-old")))
                await mailbox.turn(mailbox.add(PARTNER, remote.format(slot="wrong", language="en", request=fields["request_id"])))
                self.assertFalse([o for row in mailbox.sent if row.recipient == CITIZEN for o in cup._offer_blocks(row.text)])
                await mailbox.turn(mailbox.add(PARTNER, remote.format(slot="matching", language=language, request=fields["request_id"])))
                offers = [o for row in mailbox.sent if row.recipient == CITIZEN for o in cup._offer_blocks(row.text)]
                self.assertEqual([o["slot_id"] for o in offers], ["matching"])

    async def test_strict_live_fields_and_combined_preference(self):
        mailbox = Mailbox("strict", "B", [
            slot("fit", "asst-bicocca-h1", "25T10:00", "wed", live=True, extra="capacity=1"),
            slot("wrong-day", "asst-bicocca-h1", "24T09:00", "tue", live=True),
            slot("inconsistent-day", "asst-bicocca-h1", "24T10:00", "wed", live=True),
            slot("wrong-gender", "asst-bicocca-h2", "25T09:00", "wed", live=True),
            slot("too-late", "asst-bicocca-h1", "25T14:00", "wed", live=True),
            slot("full", "asst-bicocca-h1", "25T11:00", "wed", live=True, extra="capacity=0"),
        ])
        offers = await mailbox.offer("lang=en gender_preference=f days=wed")
        self.assertEqual([(offer["slot_id"], offer["priority"]) for offer in offers], [("fit", "B")])

    async def test_l5_183_real_italian_request_without_days_or_gender(self):
        cardiac = slot("cardiac", "s1", "25T10:00", "wed", live=True).replace("VIS-FIS", "VIS-CARD")
        mailbox = Mailbox("actual-183", "B", [cardiac], procedure="VIS-CARD")
        offers = await mailbox.offer(
            "lang=it Egregi, vi prego di volermi fissare un appuntamento per una visita specialistica. "
            "Sento il cuore accelerato e desidererei un controllo."
        )
        self.assertEqual([(offer["slot_id"], offer["agenda_day"], offer["priority"]) for offer in offers],
                         [("cardiac", "wed", "B")])

    async def test_latest_preferences_are_normalized(self):
        mailbox = Mailbox("updated", "B", [
            slot("new", "h1", "25T09:00", "wed"),
            slot("old", "h2", "25T10:00", "wed"),
        ])
        mailbox.add(CITIZEN, f"need.request prescription_number={RX} lang=it gender=m")
        offers = await mailbox.offer("lang=EN gender_preference=F days=WED")
        self.assertEqual([offer["slot_id"] for offer in offers], ["new"])

    async def test_relaxes_days_before_widening_the_window(self):
        mailbox = Mailbox("relaxed-days", "B", [
            slot("other-day", "h1", "24T09:00", "tue"),
            slot("too-late", "h1", "25T15:00", "wed"),
            slot("wrong-doctor", "h2", "25T09:00", "wed"),
        ])
        offers = await mailbox.offer("lang=en gender=f days=wed")
        self.assertEqual([(offer["slot_id"], offer["relaxed"]) for offer in offers], [("other-day", "true")])

    async def test_refreshed_page_does_not_revive_removed_slot(self):
        removed = slot("removed", "h1", "25T09:00", "wed")
        current = slot("current", "h1", "25T10:00", "wed")
        mailbox = Mailbox("refresh", "B", [removed], [])
        mailbox.add(LEDGER, "slots page=1/2\n" + current)
        offers = await mailbox.offer("lang=en gender=f days=wed")
        self.assertEqual([offer["slot_id"] for offer in offers], ["current"])

    async def test_relaxed_urgent_keeps_reserve_and_previous_pages(self):
        mailbox = Mailbox("relaxed-pages", "U", [
            slot("later-reserved", "h1", "24T09:00", "tue", extra="urgent_reserve=true"),
        ], [slot("wrong-language", "h2", "25T10:00", "wed")])
        offers = await mailbox.offer("lang=en gender=f days=mon")
        self.assertEqual([(offer["slot_id"], offer["priority"], offer["relaxed"]) for offer in offers],
                         [("later-reserved", "U", "true")])

    async def test_partner_checks_all_criteria_on_same_offer(self):
        mailbox = Mailbox("remote", "B")
        mailbox.add(CITIZEN, f"need.request prescription_number={RX} lang=EN gender=F days=wed")
        candidates = [
            ("fit", "25T10:00", "it/EN", "F"),
            ("wrong-day", "24T09:00", "en", "f"),
            ("wrong-language", "25T11:00", "it", "f"),
            ("wrong-gender", "25T11:00", "en", "m"),
            ("too-late", "25T15:00", "en", "f"),
        ]
        mailbox.add(PARTNER, "\n".join(
            f"offer offer_id=of-{name} slot_id={name} doctor_id=D-3 facility={PARTNER} procedure=VIS-FIS "
            f"agenda_date=2026-11-{time}:00Z doctor_lang={lang} doctor_gender={gender} request_id=rq-fixture"
            for name, time, lang, gender in candidates
        ))
        slots, _ = cup._cup_partner_slots(
            mailbox.rows, {PARTNER: "rq-fixture"}, "VIS-FIS", "B", datetime.fromisoformat(NOW), CITIZEN, set(),
        )
        self.assertEqual([option["slot_id"] for option in slots], ["fit"])


    async def test_partner_reserve_alias_only_allows_urgent_priority(self):
        mailbox = Mailbox("reserve", "B")
        mailbox.add(CITIZEN, f"need.request prescription_number={RX} lang=it")
        mailbox.add(
            PARTNER,
            f"offer offer_id=of-res slot_id=reserved doctor_id=h1 facility={PARTNER} procedure=VIS-FIS "
            "agenda_date=2026-11-23T17:30:00Z reserve=U request_id=rq-fixture",
        )
        params = (mailbox.rows, {PARTNER: "rq-fixture"}, "VIS-FIS")
        args = (datetime.fromisoformat(NOW), CITIZEN, set())
        self.assertEqual(cup._cup_partner_slots(*params, "B", *args)[0], [])
        self.assertEqual([slot["slot_id"] for slot in cup._cup_partner_slots(*params, "U", *args)[0]], ["reserved"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
