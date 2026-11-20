"""Confronta il consultorio completo e quello ridotto: stessi messaggi su stessi scenari.

Uso: python tools/confronto_consultorio.py <file completo salvato> <file ridotto>
Esce con il numero di scenari DIVERSI. Se non e' 0, non pubblicare.
"""

import asyncio
import importlib.util
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FULL, SMALL = sys.argv[1:3]
sys.argv = [sys.argv[0]]
spec = importlib.util.spec_from_file_location("tf", os.path.join(REPO, "tools", "test_facility.py"))
tf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tf)

ME = "agent:t02/family_counseling"
CIT = "citizen:W01QQQ-11-000105"
CUP = "agent:t02/booking_centre"
ROW = "slot_id=C-1 doctor_id=asst-bicocca-c1 facility=ME procedure=CONS-GIN at=2026-11-24T09:00:00+01:00 day=tue free=1"
TESTO_105 = "ciao raga, dovrei prenotare una visita al consultorio, lowkey urgente tipo."
CONFERMA = "confirm offer_id=of-C-1 consent_ref=cons-N-booking"
SCENARI = {
    "testo vero del 105": ([(CIT, TESTO_105)], {}),
    "conferma": ([(CIT, TESTO_105), (CIT, CONFERMA)], {}),
    "conferma, hold rifiutato": ([(CIT, TESTO_105), (CIT, CONFERMA)], {"hold": "NO_CAPACITY"}),
    "conferma e check-in": ([(CIT, TESTO_105), (CIT, CONFERMA), (CIT, "checkin booking_id=BK-H-1")], {}),
    "ricerca di un CUP esterno": ([(CUP, "need.request service_type=family_counseling.gynecology "
                                         "procedure=CONS-GIN priority=D request_id=rq-F1")], {}),
    "annullamento del CUP esterno": ([(CUP, "need.request service_type=family_counseling.gynecology "
                                            "procedure=CONS-GIN priority=D request_id=rq-F1"),
                                      (CUP, "cancel offer_id=of-C-1 slot_id=C-1 reason=slot_taken")], {}),
}


async def run(path, steps, refuse):
    tf.AGENT_FILE = path
    h = tf.Harness("family_counseling.gynecology", ME,
                   tf.World(ME, {"CONS-GIN:1": tf.slots_reply(ME, [ROW])}, refuse=refuse))
    for sender, text in steps:
        await h.turn(sender, text)
    return [re.sub(r"[0-9a-f]{8,}", "ID", f"{r.sender}>{r.recipient} {r.text}") for r in h.port.log]


async def go():
    bad = 0
    for name, (steps, refuse) in SCENARI.items():
        out = [await run(p, steps, refuse) for p in (FULL, SMALL)]
        same = out[0] == out[1]
        bad += not same
        print(("UGUALE " if same else "DIVERSO ") + name, len(out[0]), "messaggi")
        if not same:
            print("  completo:", out[0])
            print("  ridotto: ", out[1])
    sys.exit(bad)


asyncio.run(go())
