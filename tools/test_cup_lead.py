"""Le 4 ore di anticipo sono una preferenza, il minimo e' 1 ora; la scadenza si ricontrolla al confirm.

Uso, dalla cartella della repo: python tools/test_cup_lead.py
Prima il CUP scartava ogni posto libero e compatibile a meno di 4 ore d'agenda (alle 13:00 perdeva un
h1 inglese libero alle 14:30), teneva un posto di un partner con capacity=0 e confermava un orario
nel frattempo passato. Ora: i posti a 1-4 ore sono tenuti ma vengono dopo gli altri; sotto 1 ora no
(hold e commit consumano tempo reale); un partner con capacity=0 e' pieno; al confirm, un orario che
non e' piu' ad almeno 1 ora d'agenda riceve un cancel e una nuova ricerca, non un confirm.
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from city_sdk.city import City, Message, Need

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_cup_l5_vincoli as base  # noqa: E402  (riusa il Ledger finto del test L5, senza modificarlo)

cup = base.cup
TZ = timezone(timedelta(hours=1))
NOW = datetime(2026, 11, 23, 13, 0, tzinfo=TZ)  # lunedi' 13:00 d'agenda


def line(slot_id, when, day, doc="asst-bicocca-h1"):
    return (f"slot_id={slot_id} doctor_id={doc} facility={base.HOSPITAL} procedure=VIS-FIS "
            f"at={when} day={day} free=1")


NEAR = line("near", "2026-11-23T14:30:00+01:00", "mon")      # tra 1 ora e mezza
LATER = line("later", "2026-11-23T18:00:00+01:00", "mon")    # tra 5 ore
TUE = line("tue", "2026-11-24T10:00:00+01:00", "tue")
TOO_NEAR = line("too-near", "2026-11-23T13:30:00+01:00", "mon")  # tra mezz'ora


class LeadTests(unittest.TestCase):
    def test_slot_within_four_hours_is_kept(self):
        got = cup.fitting([NEAR], now=NOW, priority="B", lang="en")
        self.assertEqual([s["slot_id"] for s in got], ["near"])

    def test_four_hours_are_a_preference_not_a_filter(self):
        got = cup.fitting([NEAR, TUE, LATER], now=NOW, priority="B", lang="en")
        self.assertEqual([s["slot_id"] for s in got], ["later", "tue", "near"])

    def test_less_than_one_hour_is_dropped(self):
        got = cup.fitting([TOO_NEAR, LATER], now=NOW, priority="B", lang="en")
        self.assertEqual([s["slot_id"] for s in got], ["later"])

    def test_partner_slots_follow_the_same_rule_and_capacity_zero_is_full(self):
        partner = "agent:altra/hospital"
        citizen = "citizen:t/c-1"

        def offer(offer_id, slot_id, when, day, extra=""):
            return (f"offer offer_id={offer_id} slot_id={slot_id} doctor_id=asst-x-h1 facility={partner} "
                    f"procedure=VIS-FIS agenda_date={when} agenda_day={day} priority=B request_id=rq-1 "
                    f"doctor_lang=it/en {extra}")

        text = "\n".join([
            offer("po-near", "P-near", "2026-11-23T14:30:00+01:00", "mon"),
            offer("po-full", "P-full", "2026-11-23T18:00:00+01:00", "mon", "capacity=0"),
            offer("po-free", "P-free", "2026-11-24T10:00:00+01:00", "tue", "capacity=1"),
        ])
        chat = [
            Message(type="chat", sender=citizen, recipient="agent:noi/cup", msg_id="m1", need_id="N-1",
                    body={"text": "need.request lang=en"}),
            Message(type="chat", sender=partner, recipient="agent:noi/cup", msg_id="m2", need_id="N-1",
                    body={"text": text}),
        ]
        slots, _ = cup._cup_partner_slots(chat, {partner: "rq-1"}, "VIS-FIS", "B", NOW, citizen, set())
        self.assertNotIn("P-full", [s["slot_id"] for s in slots], "capacity=0: il posto e' pieno")
        self.assertEqual([s["slot_id"] for s in slots], ["P-free", "P-near"],
                         "le 4 ore sono una preferenza anche per i partner: P-near dopo gli altri")


class ConfirmDeadlineTests(unittest.IsolatedAsyncioTestCase):
    async def confirm(self, slot_when):
        box = base.Mailbox("confirm-" + slot_when[:13], "B", [])
        slot = {"slot_id": "S-x", "doctor_id": "asst-bicocca-h1", "facility": base.HOSPITAL,
                "procedure": "VIS-FIS", "at": slot_when, "day": "mon"}
        box.add(base.AGENT, cup._offer_line(slot, base.RX, "B", offer_id="of-x"), base.CITIZEN)
        inbound = box.add(base.CITIZEN, "confirm offer_id=of-x consent_ref=cons-1")
        city = City(index=box, history=box, messages=box, agent_id=base.AGENT, inbound=inbound)
        with patch.dict(os.environ, {"CITY_ROLE": "booking_centre"}), patch.object(cup, "_CUP_RING", ()):
            await cup.main(Need(message=inbound), city)
        return box

    async def test_slot_still_ahead_is_confirmed(self):
        box = await self.confirm("2026-11-23T18:00:00Z")
        self.assertTrue([r for r in box.sent if r.recipient == base.HOSPITAL and r.text.startswith("confirm")])

    async def test_slot_now_too_close_is_not_confirmed(self):
        box = await self.confirm("2026-11-23T13:30:00Z")
        self.assertFalse([r for r in box.sent if r.recipient == base.HOSPITAL], "nessun confirm alla struttura")
        cancels = [r.text for r in box.sent if r.recipient == base.CITIZEN and r.text.startswith("cancel")]
        self.assertEqual(len(cancels), 1)
        self.assertIn("offer_id=of-x", cancels[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
