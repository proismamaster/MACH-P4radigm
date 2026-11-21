"""Specialista: Ledger lento (40-220 s), contesa sugli slot e ricerche dei CUP partner (21/11).

Misure di Alberto sulla cronologia dello specialista: hold NO_CAPACITY 112, commit STALE_FENCE 17 su 24
(`held` -> commit 61-87 s); un hold regge circa 2 minuti. La risposta del Ledger e' nella cronologia appena
il Relay la accetta, il push che apre il turno arriva 60-90 s dopo. I CUP delle altre squadre aspettano le
risposte dei partner 15-20 s: una ricerca che rilegge agenda e world dal Ledger risponde troppo tardi.

Uso: python tools/test_specialist_attese.py
"""
import asyncio
import importlib.util
import os
import sys

from city_sdk.city import LEDGER, Message

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("tfix", os.path.join(REPO, "tools", "test_fix.py"))
tfix = importlib.util.module_from_spec(spec)
sys.argv = [sys.argv[0]]
src = open(spec.origin, encoding="utf-8").read().replace("asyncio.run(main())", "pass")
exec(compile(src, spec.origin, "exec"), tfix.__dict__)
tf = tfix.tf

SPEC = "agent:t02/specialist"
CUP = "agent:t02/booking_centre"
PARTNER = "agent:t01/booking_centre"
CIT = "citizen:t01/c-0042"
FAILS = []
ROWS = [
    "slot_id=K-1 doctor_id=asst-bicocca-s1 facility=ME procedure=VIS-CARD at=2026-11-24T09:00:00+01:00 day=tue free=1",
    "slot_id=K-2 doctor_id=asst-bicocca-s2 facility=ME procedure=VIS-CARD at=2026-11-24T10:00:00+01:00 day=tue free=1",
]


def check(name, cond, h=None):
    print(("  PASS " if cond else "  FAIL ") + name)
    if not cond:
        FAILS.append(name)
        if h:
            h.dump()


def specialist(need="N-2026-11-23-0001"):
    h = tfix.harness("specialist_care.cardiology", SPEC)
    h.need = need
    h.mod._PULL_PAUSE = 0
    return h


def confirm(offer="of-abc-1", citizen=CIT, slot="K-1"):
    return (f"confirm offer_id={offer} slot_id={slot} citizen={citizen} consent_ref=cons-N-booking "
            f"facility={SPEC} prescription_number=prescription_number-N-1")


async def main():
    print("Specialista - attesa paziente del Ledger")
    real = importlib.util.spec_from_file_location("spec_real", os.path.join(REPO, "asst", "specialist", "agent", "agent.py"))
    mod = importlib.util.module_from_spec(real)
    os.environ["CITY_ROLE"] = "specialist_care"
    real.loader.exec_module(mod)
    check("valore vero: attesa del Ledger di almeno 420 s", getattr(mod, "_WAIT_SECONDS", 0) >= 420)

    h = specialist()
    h.world = tf.Silent(SPEC)
    h.port = tf.LatePort(SPEC, tfix.World(SPEC))
    h.mod._WAIT_SECONDS, h.mod._WAIT_STEP = 5.0, 0.0
    await h.turn(CUP, confirm())
    check("held solo nella cronologia: hold, commit e ricevuta nello stesso turno del confirm",
          len(h.out(LEDGER, "hold")) == 1 and len(h.out(LEDGER, "commit")) == 1
          and len(h.out(CUP, "booking.receipt")) == 1, h)

    print("Specialista - rifiuti del Relay e slot gia' presi")
    for code, word in (("NO_CAPACITY", "cancel"), ("EXPIRED", "hold_refused")):
        h = specialist()
        h.port = tf.FlakyPort(SPEC, hold_error=code)
        await h.turn(CUP, confirm())
        back = h.out(CUP, word)
        check(f"hold rifiutato subito dal Relay ({code}): il CUP riceve {word} per of-abc-1",
              len(back) == 1 and "offer_id=of-abc-1" in back[0].split(), h)

    h = specialist("N-2026-11-23-000A")
    h.world = tf.Silent(SPEC)
    await h.turn(CUP, confirm())
    h.need = "N-2026-11-23-000B"
    await h.turn(CUP, confirm("of-def-1", "citizen:t01/c-0043"))
    back = h.out(CUP, "cancel")
    check("slot tenuto da un altro caso: cancel no_capacity subito, un solo hold",
          len(h.out(LEDGER, "hold")) == 1 and len(back) == 1 and "reason=no_capacity" in back[0].split()
          and "offer_id=of-def-1" in back[0].split(), h)

    print("Specialista - ricerche dei CUP partner")
    h = specialist("N-2026-11-23-000S")
    h.world = tfix.World(SPEC, {"VIS-CARD:1": tf.slots_reply(SPEC, ROWS)})
    search = "need.request service_type=specialist_care.cardiology procedure=VIS-CARD priority=D request_id={r}"
    await h.turn(PARTNER, search.format(r="rq-S1"))
    h.need, h.world = "N-2026-11-23-000T", tf.Silent(SPEC)
    before = len(h.out(LEDGER))
    await h.turn(PARTNER, search.format(r="rq-S2"))
    second = " ".join(t for t in h.out(PARTNER) if "rq-S2" in t)
    check("seconda ricerca in un altro caso: offerte subito da agenda e pagina gia' lette, senza il Ledger",
          "slot_id=K-" in second and "offer" in second.split() and len(h.out(LEDGER)) == before, h)
    print("FALLITE:", FAILS if FAILS else "nessuna")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    asyncio.run(main())
