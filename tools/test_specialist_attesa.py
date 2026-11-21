"""Specialist: a slow Ledger. The held line lands in the case history after the quick reads, and
the push that would open the next turn comes 60-90 s later, after the hold (about 2 minutes) has
lapsed. The confirm turn must keep reading the history, then commit and send the receipt.

Uso: python tools/test_specialist_attesa.py
"""
import asyncio
import importlib.util
import os
import sys
import time

from city_sdk.city import LEDGER, Message

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("spec_att", os.path.join(REPO, "asst", "specialist", "agent", "agent.py"))
mod = importlib.util.module_from_spec(spec)
sys.modules["spec_att"] = mod
spec.loader.exec_module(mod)
mod._PULL_PAUSE = 0
mod._WAIT_SECONDS, mod._WAIT_STEP = 0.5, 0.0  # the real 180 s wait, scaled down

ME = "agent:sh35cbsy287d"
CUP = "agent:altra/cup"
CIT = "citizen:t/c-5"
FAILS = []


def check(name, cond):
    print(("  PASS " if cond else "  FAIL ") + name)
    if not cond:
        FAILS.append(name)


def msg(i, sender, recipient, text):
    return Message(type="chat", sender=sender, recipient=recipient, msg_id=f"a{i}", need_id="N-A", body={"text": text})


CASE = [
    msg(1, CUP, ME, f"confirm offer_id=of-A slot_id=S-A citizen={CIT} consent_ref=cx-a prescription_number=RX-A"),
    msg(2, ME, LEDGER, f"hold slot_id=S-A citizen={CIT} prescription_number=RX-A consent_ref=cx-a"),
]
HELD = msg(3, LEDGER, ME, "held hold_id=H-A slot_id=S-A fence=1")
COMMITTED = msg(5, LEDGER, ME, "committed booking_id=H-A ledger_ref=L-A hold_id=H-A")


class FakeCity:
    agent_id = ME

    def __init__(self, held_after):
        self.reads, self.held_after, self.sent = 0, held_after, []

    async def say(self, to, text, **_):
        self.sent.append((to, text))
        return f"m{len(self.sent)}"

    async def history(self, peer=None, *, need_id=None):
        self.reads += 1
        rows = list(CASE)
        if self.reads > self.held_after:
            rows.append(HELD)
        commits = [t for to, t in self.sent if to == LEDGER and t.startswith("commit ")]
        if commits:
            rows += [msg(4, ME, LEDGER, commits[0]), COMMITTED]
        return rows


def run(held_after):
    city = FakeCity(held_after)
    started = time.monotonic()
    asyncio.run(mod._finish_booking(city, CASE[0], list(CASE), "S-A", hold_self=False))
    commits = [t for to, t in city.sent if to == LEDGER and t.startswith("commit ")]
    receipts = [t for to, t in city.sent if to == CUP and t.startswith("booking.receipt")]
    return commits, receipts, time.monotonic() - started


print("Specialist - held dopo le letture rapide (Ledger lento)")
commits, receipts, _ = run(held_after=40)  # the quick reads are 24
check("held alla lettura 41: commit dell'hold nello stesso turno", len(commits) == 1 and "hold_id=H-A" in commits[0])
check("committed: ricevuta al CUP con slot_id", len(receipts) == 1 and "slot_id=S-A" in receipts[0])
commits, receipts, took = run(held_after=10 ** 9)
check("held mai arrivato: nessun commit", commits == [] and receipts == [])
check("held mai arrivato: il turno finisce entro l'attesa", took < 3.0)

print("FALLITE:", FAILS if FAILS else "nessuna")
sys.exit(1 if FAILS else 0)
