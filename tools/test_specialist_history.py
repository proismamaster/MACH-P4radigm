"""Specialist: a 504 from city.history() at the start of the turn.

Uso: python tools/test_specialist_history.py
"""
import asyncio
import importlib.util
import os
import sys

os.environ["CITY_ROLE"] = "specialist_care"

from city_sdk.city import LEDGER, CapError, Message, Need

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("spec_hist", os.path.join(REPO, "asst", "specialist", "agent", "agent.py"))
mod = importlib.util.module_from_spec(spec)
sys.modules["spec_hist"] = mod
spec.loader.exec_module(mod)
mod._PULL_PAUSE = 0
mod._WAIT_SECONDS = 0.0  # niente attesa paziente del Ledger nelle prove (la vera e' 420 s)

ME = "agent:sh35cbsy287d"
CUP = "agent:altra/cup"
CIT = "citizen:t/c-7"
FAILS = []


def check(name, cond):
    print(("  PASS " if cond else "  FAIL ") + name)
    if not cond:
        FAILS.append(name)


def msg(i, sender, recipient, text):
    return Message(type="chat", sender=sender, recipient=recipient, msg_id=f"h{i}", need_id="N-H", body={"text": text})


# A hold we sent, its held line, no commit yet: the case a later turn must finish.
CASE = [
    msg(1, CUP, ME, f"confirm offer_id=of-H slot_id=S-H citizen={CIT} consent_ref=cx-h prescription_number=RX-H"),
    msg(2, ME, LEDGER, f"hold slot_id=S-H citizen={CIT} prescription_number=RX-H consent_ref=cx-h"),
    msg(3, LEDGER, ME, "held hold_id=H-H slot_id=S-H"),
]
INBOUND = msg(9, CIT, ME, "Buongiorno, volevo sapere se la visita è confermata.")


class FakeCity:
    agent_id = ME

    def __init__(self, errors):
        self.errors = list(errors)  # one CapError code per failing history() call, then success
        self.calls = 0
        self.sent = []
        self.inbound = INBOUND

    async def say(self, to, text, **_):
        self.sent.append((to, text))
        return f"m{len(self.sent)}"

    async def history(self, peer=None, *, need_id=None):
        self.calls += 1
        if self.errors:
            raise CapError(self.errors.pop(0))
        return [*CASE, INBOUND]


def run(errors):
    city = FakeCity(errors)
    try:
        asyncio.run(mod.main(Need(summary=INBOUND.text, message=INBOUND), city))
    except CapError as error:  # the turn may end with the error; what matters is what was sent
        city.raised = error.code
    commits = [t for to, t in city.sent if to == LEDGER and t.startswith("commit ")]
    receipts = [t for to, t in city.sent if t.startswith("booking.receipt")]
    return city, commits, receipts


print("Specialist - 504 su city.history() all'inizio del turno")
city, commits, receipts = run(["UPSTREAM_TIMEOUT"])
check("504 poi lettura riuscita: un solo commit dell'hold rimasto", len(commits) == 1 and "hold_id=H-H" in commits[0])
check("504 poi lettura riuscita: due letture", city.calls == 2)
city, commits, receipts = run(["UPSTREAM_TIMEOUT", "UPSTREAM_TIMEOUT"])
check("due 504: nessun commit e nessuna ricevuta su dati mancanti", commits == [] and receipts == [] and city.sent == [])
check("due 504: al massimo due letture", city.calls == 2)
city, commits, receipts = run(["GRANT_PERMISSION_DENIED"])
check("4xx: nessun retry (una sola lettura) e nessun invio", city.calls == 1 and city.sent == [])

print("FALLITE:", FAILS if FAILS else "nessuna")
sys.exit(1 if FAILS else 0)
