"""Il CUP non scarta gli orari con id medico fuori dalla tabella scritta a mano.

Uso, dalla cartella della repo: python tools/test_cup_medici.py
L'esempio del kit usa doctor_id=D-3: prima della correzione il CUP scartava tutti questi orari,
sia della propria ASST (fitting) sia dei partner (_cup_partner_slots).
"""

import importlib.util
import os
import sys
from datetime import datetime, timedelta, timezone

from city_sdk.city import Message

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location(
    "cup", os.path.join(REPO, "asst", "booking_centre", "agent", "agent.py"))
cup = importlib.util.module_from_spec(spec)
sys.modules["cup"] = cup  # dataclasses need the module registered
spec.loader.exec_module(cup)

FAILS = []


def check(name, cond):
    print(("  PASS " if cond else "  FAIL ") + name)
    if not cond:
        FAILS.append(name)


NOW = datetime(2026, 11, 23, 8, 0, tzinfo=timezone(timedelta(hours=1)))
AT = "2026-11-24T09:00:00+01:00"  # martedì
LINE = f"slot_id=S-1 doctor_id={{doc}} facility=agent:p/hosp procedure=VIS-FIS at={AT} day=tue free=1"

print("CUP - orari della propria ASST (fitting)")
for doc in ("D-3", "asst-x-dott-7", "h1"):
    got = cup.fitting([LINE.format(doc=doc)], now=NOW, priority="B", lang="it")
    check(f"tiene l'orario con doctor_id={doc}", len(got) == 1)
got = cup.fitting([LINE.format(doc="D-3")], now=NOW, priority="B", lang="it", gender="f")
check("medico sconosciuto e preferenza di genere: scartato (non verificabile)", got == [])
got = cup.fitting([LINE.format(doc="D-3")], now=NOW, priority="B", lang="ar")
check("medico sconosciuto e lingua rara: scartato (non verificabile)", got == [])
got = cup.fitting([LINE.format(doc="h2")], now=NOW, priority="B", lang="it")
check("medico noto fuori dai suoi giorni (h2 non lavora il martedì): scartato", got == [])

print("CUP - orari dei partner (_cup_partner_slots)")
PARTNER = "agent:altra/hospital"
CIT = "citizen:t/c-1"
offer = (f"offer offer_id=po-1 slot_id=S-9 doctor_id=D-3 facility={PARTNER} procedure=VIS-FIS "
         f"agenda_date={AT} agenda_day=tue expiry={AT} priority=B request_id=rq-1")
chat = [
    Message(type="chat", sender=CIT, recipient="agent:noi/cup", msg_id="m1", need_id="N-1",
            body={"text": "need.request rx=prescription_number-X"}),
    Message(type="chat", sender=PARTNER, recipient="agent:noi/cup", msg_id="m2", need_id="N-1",
            body={"text": offer}),
]
slots, answered = cup._cup_partner_slots(chat, {PARTNER: "rq-1"}, "VIS-FIS", "B", NOW, CIT, set())
check("tiene l'offerta del partner con doctor_id=D-3", len(slots) == 1 and slots[0]["partner_offer_id"] == "po-1")
check("il partner risulta aver risposto", answered == {PARTNER})

print("FALLITE:", FAILS if FAILS else "nessuna")
sys.exit(1 if FAILS else 0)
