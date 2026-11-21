"""GP: il Ledger scrive `prescribed` nella storia dopo i 6 secondi di attesa e la notifica non arriva (405).

Uso: python tools/test_gp_ledger_lento.py
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

FAILS = []


def check(name, cond):
    print(("  PASS " if cond else "  FAIL ") + name)
    if not cond:
        FAILS.append(name)


async def scenario(late_after):
    h = tfix.harness("gp", tfix.GP, role_card="gp")
    h.mod._PULL_PAUSE = 0
    h.mod._PULL_TRIES = 24  # the real value: the harness sets 1 to skip waits
    if hasattr(h.mod, "_RX_STEP"):
        h.mod._RX_WAIT, h.mod._RX_STEP = 5.0, 0.001  # the real 90 s wait, scaled down (Windows sleeps ~15 ms)
    world = h.world
    h.world.answer = lambda text: None if text.startswith("prescribe") else tfix.World.answer(world, text)
    reads = {"n": 0}
    original = h.port.history

    async def history(*, peer=None, need_id=None):
        rows = await original(peer=peer, need_id=need_id)
        sent = [r for r in h.port.log if r.recipient == LEDGER and r.text.startswith("prescribe ")]
        if sent:
            reads["n"] += 1
            if reads["n"] == late_after:
                f = dict(w.split("=", 1) for w in sent[0].text.split()[1:] if "=" in w)
                h.port.log.append(Message(
                    type="chat", sender=LEDGER, recipient=h.me, msg_id="late-rx", need_id=h.need, conversation_id="c-1",
                    body={"text": f"prescribed prescription_number={f['prescription_number']} patient={f['patient']} "
                                  f"procedure={f['procedure']} priority={f['priority']} state=issued"}))
                rows = await original(peer=peer, need_id=need_id)
        return rows

    h.port.history = history
    await h.turn(tfix.CIT, "Ho mal di schiena da settimane")
    return h


async def main():
    print("GP - prescribed scritto tardi nella storia, nessuna notifica (405)")
    h = await scenario(late_after=30)
    check("ricetta annunciata nello stesso turno anche se il Ledger risponde dopo 6 s", len(h.out(tfix.CIT, "prescription")) == 1)
    h = await scenario(late_after=3)
    check("risposta rapida: una sola ricetta", len(h.out(tfix.CIT, "prescription")) == 1)
    print("FALLITE:", FAILS if FAILS else "nessuna")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    asyncio.run(main())
