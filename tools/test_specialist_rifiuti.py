"""Specialist: a late Ledger refusal cancels the offer it refers to, with its own code.

Uso: python tools/test_specialist_rifiuti.py
"""
import asyncio
import importlib.util
import os
import sys

from city_sdk.city import LEDGER, Message

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("spec_rif", os.path.join(REPO, "asst", "specialist", "agent", "agent.py"))
mod = importlib.util.module_from_spec(spec)
sys.modules["spec_rif"] = mod
spec.loader.exec_module(mod)

ME = "agent:sh35cbsy287d"
CUP = "agent:altra/cup"
CIT = "citizen:t/c-1"
FAILS = []


def check(name, cond):
    print(("  PASS " if cond else "  FAIL ") + name)
    if not cond:
        FAILS.append(name)


class FakeCity:
    agent_id = ME

    def __init__(self):
        self.sent = []

    async def say(self, to, text, **_):
        self.sent.append((to, text))
        return f"m{len(self.sent)}"

    async def history(self, need_id=None):
        return []


def msg(i, sender, recipient, text):
    return Message(type="chat", sender=sender, recipient=recipient, msg_id=f"x{i}", need_id="N-1", body={"text": text})


# Two cross-ASST confirms for the same citizen: the first hold (S-OLD) is refused late,
# after the second hold (S-NEW) was already sent.
CHAT = [
    msg(1, CUP, ME, f"confirm offer_id=of-OLD slot_id=S-OLD citizen={CIT} consent_ref=cx-1 prescription_number=RX-1"),
    msg(2, ME, LEDGER, f"hold slot_id=S-OLD citizen={CIT} prescription_number=RX-1 consent_ref=cx-1"),
    msg(3, LEDGER, ME, "held hold_id=H-OLD slot_id=S-OLD"),
    msg(4, CUP, ME, f"confirm offer_id=of-NEW slot_id=S-NEW citizen={CIT} consent_ref=cx-1 prescription_number=RX-1"),
    msg(5, ME, LEDGER, f"hold slot_id=S-NEW citizen={CIT} prescription_number=RX-1 consent_ref=cx-1"),
]


def run(refusal, chat=CHAT):
    city = FakeCity()
    row = msg(9, LEDGER, ME, refusal)
    asyncio.run(mod._facility(city, row, [*chat, row], reports=True, hold_self=False))
    return [t for to, t in city.sent if to == CUP]


print("Specialist - rifiuto tardivo del Ledger")
out = run("refused hold slot_id=S-OLD code=NO_CAPACITY")
check("rifiuto di S-OLD: annulla of-OLD, non of-NEW", out and "offer_id=of-OLD" in out[0] and "of-NEW" not in out[0])
check("verso un CUP: codice conservato (no_capacity) e slot_id", out and "no_capacity" in out[0] and "slot_id=S-OLD" in out[0])
out = run("refused commit hold_id=H-OLD code=PRESCRIPTION_EXPIRED")
check("rifiuto per hold_id: risale a S-OLD", out and "offer_id=of-OLD" in out[0] and "prescription_expired" in out[0])
out = run("refused hold slot_id=S-OLD code=WEIRD_CODE")
check("codice sconosciuto: hold_refused con ledger_code originale", out and out[0].startswith("hold_refused") and "ledger_code=WEIRD_CODE" in out[0])
out = run("refused commit hold_id=H-OLD code=DUPLICATE")
check("DUPLICATE sul commit: nessun annullamento", out == [])
receipt = msg(6, ME, CUP, "booking.receipt booking_id=bk-1 ledger_ref=L-1 slot_id=S-OLD offer_id=of-OLD")
out = run("refused hold slot_id=S-OLD code=NO_CAPACITY", [*CHAT, receipt])
check("dopo una ricevuta valida: nessun annullamento", out == [])

print("Specialist - ricevuta cross-ASST con slot_id")
city = FakeCity()
row = msg(9, LEDGER, ME, "committed booking_id=bk-2 ledger_ref=L-2 hold_id=H-OLD")
asyncio.run(mod._facility(city, row, [*CHAT, row], reports=True, hold_self=False))
out = [t for to, t in city.sent if to == CUP]
check("ricevuta al CUP con slot_id e offer_id", out and "slot_id=S-OLD" in out[0] and "offer_id=of-OLD" in out[0])

print("Specialist - ricevuta al cittadino senza slot_id")
cchat = [
    msg(11, CIT, ME, "confirm offer_id=of-C slot_id=S-C consent_ref=cx-2"),
    msg(12, ME, LEDGER, f"hold slot_id=S-C citizen={CIT} consent_ref=cx-2"),
    msg(13, ME, CIT, "booking.receipt booking_id=bk-9 ledger_ref=L-9"),
]
city = FakeCity()
row = msg(19, LEDGER, ME, "refused hold slot_id=S-C code=NO_CAPACITY")
asyncio.run(mod._facility(city, row, [*cchat, row], reports=True, hold_self=False))
check("rifiuto tardivo dopo la ricevuta al cittadino: nessun annullamento", not [t for to, t in city.sent if to == CIT])

print("FALLITE:", FAILS if FAILS else "nessuna")
sys.exit(1 if FAILS else 0)
