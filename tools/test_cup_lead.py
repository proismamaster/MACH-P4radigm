"""Anticipo degli slot in ore d'agenda: preferiti a 30 ore o piu', minimo 4 ore; scadenza ricontrollata al confirm.

Uso, dalla cartella della repo: python tools/test_cup_lead.py
Un minuto reale e' un'ora d'agenda e il cittadino risponde dopo 3-27 minuti: gli slot offerti a poche
ore sono gia' passati quando decide (console 21/11: rifiuti `past`, `EXPIRED` al hold). Ora: si offrono
per primi gli slot ad almeno 30 ore d'agenda (il weekend non conta), poi quelli ad almeno 4 ore, mai
quelli sotto le 4 ore; un partner con capacity=0 e' pieno; al confirm, un orario che non e' piu' ad
almeno 4 ore d'agenda riceve un cancel e una nuova ricerca, non un confirm.
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


NEAR = line("near", "2026-11-23T14:30:00+01:00", "mon")      # tra 1 ora e mezza: mai
LATER = line("later", "2026-11-23T18:00:00+01:00", "mon")    # tra 5 ore
TUE = line("tue", "2026-11-24T10:00:00+01:00", "tue")        # tra 21 ore
WED = line("wed", "2026-11-25T10:00:00+01:00", "wed")        # tra 45 ore: preferito
TOO_NEAR = line("too-near", "2026-11-23T13:30:00+01:00", "mon")  # tra mezz'ora


class LeadTests(unittest.TestCase):
    def test_slot_closer_than_ten_hours_is_dropped(self):
        got = cup.fitting([NEAR, TOO_NEAR, LATER, TUE], now=NOW, priority="D", lang="en")
        self.assertEqual([s["slot_id"] for s in got], ["tue"])

    def test_slots_thirty_hours_ahead_come_first(self):
        got = cup.fitting([LATER, TUE, WED], now=NOW, priority="D", lang="en")
        self.assertEqual([s["slot_id"] for s in got], ["wed", "tue"])

    def test_urgent_keeps_four_hours(self):
        got = cup.fitting([LATER, TUE], now=NOW, priority="U", lang="en")
        self.assertEqual([s["slot_id"] for s in got], ["later"])

    def test_the_weekend_does_not_count_as_agenda_time(self):
        fri = datetime(2026, 11, 20, 17, 0, tzinfo=TZ)  # venerdi' 17:00
        mon = line("mon", "2026-11-23T10:30:00+01:00", "mon")   # 17 ore e mezza d'agenda
        tue = line("tue", "2026-11-24T10:30:00+01:00", "tue")   # 41 ore e mezza
        got = cup.fitting([mon, tue], now=fri, priority="D", lang="en")
        self.assertEqual([s["slot_id"] for s in got], ["tue", "mon"])

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
            offer("po-far", "P-far", "2026-11-25T10:00:00+01:00", "wed", "capacity=1"),
        ])
        chat = [
            Message(type="chat", sender=citizen, recipient="agent:noi/cup", msg_id="m1", need_id="N-1",
                    body={"text": "need.request lang=en"}),
            Message(type="chat", sender=partner, recipient="agent:noi/cup", msg_id="m2", need_id="N-1",
                    body={"text": text}),
        ]
        slots, _ = cup._cup_partner_slots(chat, {partner: "rq-1"}, "VIS-FIS", "B", NOW, citizen, set())
        self.assertNotIn("P-full", [s["slot_id"] for s in slots], "capacity=0: il posto e' pieno")
        self.assertEqual([s["slot_id"] for s in slots], ["P-free", "P-far"],
                         "priorita' B: il piu' vicino oltre le 4 ore prima; P-near (1 ora e mezza) mai")


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
