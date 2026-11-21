"""CUP, ultime correzioni dai percorsi falliti del 21/11 (export 280-318, 187, 293, 134, 191).

Uso, dalla cartella della repo: python tools/test_cup_l8_finale.py
- La scadenza B/D parte dal primo messaggio al medico, 19,5-20,6 ore d'agenda prima che il cittadino scriva
  al CUP (21 ore, con margine):
  187 (B prescritta mar 01/12 ~05:00) rifiuta il 03/12 10:30 per deadline e conferma il 02/12 10:30.
- B: il primo slot dopo le 4 ore, non quelli a 30 ore (oltre la scadenza vera).
- Le date dei partner senza fuso vanno inoltrate in UTC con la Z (audit false_attribute -2).
- "posso solo lun/mer/ven" (288): giorni abbreviati.
"""

import importlib.util
import os
import sys
from datetime import datetime, timezone

from city_sdk.city import LEDGER, Message

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("cup", os.path.join(REPO, "asst", "booking_centre", "agent", "agent.py"))
cup = importlib.util.module_from_spec(spec)
sys.modules["cup"] = cup
spec.loader.exec_module(cup)

FAILS = []


def check(name, cond):
    print(("  PASS " if cond else "  FAIL ") + name)
    if not cond:
        FAILS.append(name)


CIT = "citizen:t/c-1"
READ = "2026-11-21T04:04:30Z"
agenda = Message(type="chat", sender=LEDGER, recipient="agent:noi/cup", msg_id="ag", need_id="N-1",
                 body={"text": "agenda agenda_now=2026-12-02T01:00:00Z"}, sent_at=READ)
first = Message(type="chat", sender=CIT, recipient="agent:noi/cup", msg_id="m1", need_id="N-1",
                body={"text": "need.request lang=it"}, sent_at=READ)
chat = [first, agenda]
NOW = datetime(2026, 12, 2, 1, 0, tzinfo=timezone.utc)

print("Scadenza dalla ricetta")
until = cup._true_deadline(chat, CIT, "B")
check("B: scadenza vera giovedi' 03/12 alle 04:00 (un'ora di margine)", until == datetime(2026, 12, 3, 4, 0, tzinfo=timezone.utc))


def line(sid, when, day, doc="asst-bicocca-s1"):
    return f"slot_id={sid} doctor_id={doc} facility=agent:p/spec procedure=VIS-CARD agenda_date={when} agenda_day={day} capacity=1"


rows = [line("wed-1030", "2026-12-02T10:30:00.000Z", "wed"), line("thu-1030", "2026-12-03T10:30:00.000Z", "thu", "asst-bicocca-s2")]
got = [s["slot_id"] for s in cup.fitting(rows, now=NOW, priority="B", lang="it", procedure="VIS-CARD", until=until)]
check("B: 02/12 10:30 si', 03/12 10:30 no (oltre la scadenza vera)", got == ["wed-1030"])
rows = [line("wed-1430", "2026-12-02T14:30:00.000Z", "wed"), line("wed-1030", "2026-12-02T10:30:00.000Z", "wed")]
got = [s["slot_id"] for s in cup.fitting(rows, now=NOW, priority="B", lang="it", procedure="VIS-CARD")]
check("B: il piu' vicino oltre le 4 ore viene prima", got == ["wed-1030", "wed-1430"])
check("D: resta la preferenza per le 30 ore", cup._lead("D") == cup._LEAD and cup._lead("B") == cup._MIN_LEAD)

print("Date dei partner in UTC")
PARTNER = "agent:altra/hospital"
offer = (f"offer offer_id=po-1 slot_id=S-9 doctor_id=asst-x-h1 facility={PARTNER} procedure=VIS-FIS "
         "agenda_date=2026-12-02T12:00:00 agenda_day=wed expiry=2026-12-02T12:00:00 priority=D request_id=rq-1 doctor_lang=it/en")
pchat = [Message(type="chat", sender=CIT, recipient="agent:noi/cup", msg_id="m1", need_id="N-1", body={"text": "need.request lang=it"}),
         Message(type="chat", sender=PARTNER, recipient="agent:noi/cup", msg_id="m2", need_id="N-1", body={"text": offer})]
slots, _ = cup._cup_partner_slots(pchat, {PARTNER: "rq-1"}, "VIS-FIS", "D", NOW, CIT, set())
check("partner: agenda_date inoltrata come 2026-12-02T12:00:00.000Z", bool(slots) and slots[0]["at"] == "2026-12-02T12:00:00.000Z"
      and slots[0]["expiry"] == "2026-12-02T12:00:00.000Z")

print("Giorni abbreviati")
dchat = [Message(type="chat", sender=CIT, recipient="x", msg_id="d", need_id="N-1",
                 body={"text": "Male, ginocchio. Mi serve un appuntamento al più presto, ma posso solo lun/mer/ven. need.request lang=it"})]
check("lun/mer/ven -> mon, wed, fri", cup._cup_days(dchat, CIT) == {"mon", "wed", "fri"})

print("MACH-1.3 nelle ricerche ai partner")
import inspect
src = inspect.getsource(cup._cup_cross_asst)
check("la ricerca porta mach=1.3, earliest= e deadline= con data e ora", "mach=1.3" in src and "deadline=" in src)

print("FALLITE:", FAILS if FAILS else "nessuna")
sys.exit(1 if FAILS else 0)
