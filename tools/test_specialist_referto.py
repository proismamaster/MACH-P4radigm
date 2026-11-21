"""Specialist: il referto si archivia anche se il cittadino non risponde al consenso.

Percorso N-2026-11-02-8909110001820005 (PROBLEMS, verdetti 06:00-08:38): check-in onorato (+2), lo
specialist chiede `consent purpose=report_sharing`, il cittadino non risponde, verdetto `report_missing -1`.
Il kit: senza il campo chiesto si archivia il referto non condiviso; aspettare una risposta che non
arriverà lascia il percorso fermo.
Dalla cartella della repo: python tools/test_specialist_referto.py
"""

import asyncio
import importlib.util
import os
import sys
from uuid import uuid4

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("tf", os.path.join(REPO, "tools", "test_facility.py"))
tf = importlib.util.module_from_spec(spec)
sys.argv = [sys.argv[0]]
spec.loader.exec_module(tf)
from city_sdk.city import LEDGER, Message  # noqa: E402

FAILS = []
SPEC = "agent:t02/specialist"
CIT = "citizen:t01/c-0042"


def check(name, cond, h=None):
    print(("  PASS " if cond else "  FAIL ") + name)
    if not cond:
        FAILS.append(name)
        if h:
            h.dump()


class World(tf.World):
    def answer(self, text):
        words = text.split()
        f = dict(w.split("=", 1) for w in words[1:] if "=" in w)
        if words[0] == "report":
            return f"reported booking_id={f['booking_id']}"
        return super().answer(text)


class AnsweringPort(tf.Port):
    """The citizen answers the consent question while the specialist is still in its turn."""

    def __init__(self, me, answer):
        super().__init__(me)
        self.answer = answer

    async def history(self, *, peer=None, need_id=None):
        asked = any(r.sender == SPEC and "purpose=report_sharing" in r.text.split() for r in self.log)
        if asked and self.answer and not any(r.sender == CIT and r.text == self.answer for r in self.log):
            self.log.append(Message(type="chat", sender=CIT, recipient=SPEC, msg_id=uuid4().hex,
                                    need_id="N-2026-11-23-0001", conversation_id="c-1", body={"text": self.answer}))
        return await super().history(peer=peer, need_id=need_id)


def harness(answer=None):
    tf.AGENT_FILE = os.path.join(REPO, "asst", "specialist", "agent", "agent.py")
    h = tf.Harness.__new__(tf.Harness)
    h.mod = tf.load("specialist_care.cardiology", SPEC)
    h.mod._CONSENT_WAIT = 0.6
    h.mod._PULL_PAUSE = 0.05
    h.me, h.world, h.need = SPEC, World(SPEC), "N-2026-11-23-0001"
    h.port = AnsweringPort(SPEC, answer)
    return h


def reports(h):
    return [r.text for r in h.port.log if r.sender == SPEC and r.recipient == LEDGER and r.text.startswith("report ")]


async def main():
    print("Specialist - referto anche senza risposta al consenso (report_missing -1)")
    h = harness()
    await h.turn(CIT, "checkin booking_id=BK-1 ledger_ref=LR-1")
    sent = reports(h)
    check("il cittadino non risponde: referto archiviato lo stesso, senza consent_ref",
          len(sent) == 1 and "booking_id=BK-1" in sent[0] and "consent_ref" not in sent[0], h)
    check("chiede comunque il consenso report_sharing",
          any("purpose=report_sharing" in t for t in h.out(CIT, "consent")), h)
    await h.turn(CIT, "consent purpose=report_sharing consent_ref=cons-late")
    check("risposta arrivata dopo il referto: nessun secondo referto", len(reports(h)) == 1, h)

    h = harness(answer="consent purpose=report_sharing consent_ref=cons-77")
    await h.turn(CIT, "checkin booking_id=BK-1 ledger_ref=LR-1")
    sent = reports(h)
    check("il cittadino acconsente subito: un referto con consent_ref=cons-77",
          len(sent) == 1 and "consent_ref=cons-77" in sent[0], h)

    h = harness(answer="No, preferisco di no.")
    await h.turn(CIT, "checkin booking_id=BK-1 ledger_ref=LR-1")
    sent = reports(h)
    check("il cittadino rifiuta a parole: un referto senza consent_ref",
          len(sent) == 1 and "consent_ref" not in sent[0], h)
    check("referto comunicato al cittadino", len(h.out(CIT, "report")) == 1, h)

    print("\nFALLITE:", FAILS if FAILS else "nessuna")
    sys.exit(1 if FAILS else 0)


asyncio.run(main())
