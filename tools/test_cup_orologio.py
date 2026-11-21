"""L'orologio d'agenda del CUP non entra nel weekend.

Uso, dalla cartella della repo: python tools/test_cup_orologio.py
L'agenda salta sabato e domenica (kit, ADR-124). _agenda_now estrapola l'ora dall'ultima risposta
del Ledger piu' il tempo reale x60: venerdi' 23:00 piu' 2 ore deve dare lunedi' 01:00, non sabato.
(L'orizzonte B/D sui giorni feriali e' gia' su main: tools/test_cup_scadenze.py.)
"""

import importlib.util
import os
import sys
from datetime import datetime, timedelta, timezone

from city_sdk.city import LEDGER, Message

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location(
    "cup", os.path.join(REPO, "asst", "booking_centre", "agent", "agent.py"))
cup = importlib.util.module_from_spec(spec)
sys.modules["cup"] = cup  # dataclasses need the module registered
spec.loader.exec_module(cup)
cup._WAIT_SECONDS = 0.0  # the fake Ledger answers in the next turn: no patient wait

FAILS = []


def check(name, cond):
    print(("  PASS " if cond else "  FAIL ") + name)
    if not cond:
        FAILS.append(name)


print("CUP - l'orologio d'agenda salta il weekend")
read = "2026-11-21T00:40:00Z"
row = Message(type="chat", sender=LEDGER, recipient="agent:noi/cup", msg_id="ag", need_id="N-1",
              body={"text": "agenda agenda_now=2026-11-20T23:00:00Z"}, sent_at=read)
later = datetime(2026, 11, 21, 0, 42, tzinfo=timezone.utc)
check("venerdi' 23:00 + 2 minuti reali (2 ore d'agenda) = lunedi' 01:00, non sabato",
      cup._agenda_now([row], later) == datetime(2026, 11, 23, 1, 0, tzinfo=timezone.utc))
row = Message(type="chat", sender=LEDGER, recipient="agent:noi/cup", msg_id="ag", need_id="N-1",
              body={"text": "agenda agenda_now=2026-11-18T09:00:00Z"}, sent_at=read)
later = datetime(2026, 11, 21, 0, 45, tzinfo=timezone.utc)
check("a meta' settimana l'orologio non cambia: mercoledi' 09:00 + 5 ore = mercoledi' 14:00",
      cup._agenda_now([row], later) == datetime(2026, 11, 18, 14, 0, tzinfo=timezone.utc))
row = Message(type="chat", sender=LEDGER, recipient="agent:noi/cup", msg_id="ag", need_id="N-1",
              body={"text": "agenda agenda_now=2026-11-20T09:00:00Z"}, sent_at=read)
later = datetime(2026, 11, 21, 0, 40, tzinfo=timezone.utc) + timedelta(minutes=30)
check("venerdi' 09:00 + 30 minuti reali (30 ore) = lunedi' 15:00",
      cup._agenda_now([row], later) == datetime(2026, 11, 23, 15, 0, tzinfo=timezone.utc))

print("FALLITE:", FAILS if FAILS else "nessuna")
sys.exit(1 if FAILS else 0)
