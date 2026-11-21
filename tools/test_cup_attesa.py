"""CUP: the Ledger's reply to the first lookup lands in the case history minutes later, and the push that
would open the next turn may never come (export 13:17 UTC: 44 of 84 failed journeys with the citizen's
need.request unanswered). The patient wait keeps reading the history; a 429 does not end it.

Uso: python tools/test_cup_attesa.py
"""
import asyncio
import importlib.util
import os
import sys
import time

from city_sdk.city import CapError, Message

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("cup_att", os.path.join(REPO, "asst", "booking_centre", "agent", "agent.py"))
cup = importlib.util.module_from_spec(spec)
sys.modules["cup_att"] = cup
spec.loader.exec_module(cup)
cup._PULL_PAUSE = 0
cup._WAIT_SECONDS, cup._WAIT_STEP, cup._WAIT_STEP_LATE = 0.5, 0.0, 0.0  # the real 420 s, scaled down
FAILS = []


def check(name, cond):
    print(("  PASS " if cond else "  FAIL ") + name)
    if not cond:
        FAILS.append(name)


REPLY = Message(type="chat", sender="city:ledger", recipient="agent:t/cup", msg_id="r1", need_id="N-1",
                body={"text": "prescription prescription_number=RX-1 procedure=VIS-CARD priority=B"})


class Fake:
    def __init__(self, ready_after, errors=()):
        self.reads, self.ready_after, self.errors = 0, ready_after, list(errors)

    async def history(self, peer=None, *, need_id=None):
        self.reads += 1
        if self.errors:
            raise CapError(self.errors.pop(0))
        return [REPLY] if self.reads > self.ready_after else []


def wait(city, **kw):
    started = time.monotonic()
    got = asyncio.run(cup._until(city, "N-1", [], lambda rows: any(r.msg_id == "r1" for r in rows), **kw))
    return got, time.monotonic() - started


print("CUP - attesa paziente della risposta del Ledger")
city = Fake(ready_after=40)
got, _ = wait(city, patient=True)
check("risposta alla lettura 41: l'attesa paziente la trova", got is not None and any(r.msg_id == "r1" for r in got))
city = Fake(ready_after=40)
got, _ = wait(city)
check("senza attesa paziente: 24 letture e basta (come prima)", city.reads == 24 and not any(r.msg_id == "r1" for r in got or []))
city = Fake(ready_after=0, errors=["RATE_LIMITED", "RATE_LIMITED"])
got, _ = wait(city, patient=True)
check("due 429 di fila non chiudono l'attesa paziente", got is not None and any(r.msg_id == "r1" for r in got))
city = Fake(ready_after=0, errors=["RATE_LIMITED"])
got, _ = wait(city)
check("senza attesa paziente un 429 chiude come prima", got is None and city.reads == 1)
city = Fake(ready_after=10 ** 9)
got, took = wait(city, patient=True)
check("risposta mai arrivata: l'attesa finisce entro _WAIT_SECONDS", took < 3.0 and not any(r.msg_id == "r1" for r in got or []))

print("FALLITE:", FAILS if FAILS else "nessuna")
sys.exit(1 if FAILS else 0)
