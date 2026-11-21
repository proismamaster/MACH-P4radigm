"""GP: le attese del Ledger e la lettura del caso a inizio turno (21/11, Ledger a 40-220 s).

1. `city.history` in 504 all'inizio del turno: prima l'eccezione usciva dal brain, l'harness la chiudeva
   come `rejected` ("agent crashed") e il messaggio del cittadino non tornava piu'. Una red flag deve
   comunque produrre l'escalation.
2. `prescribed` nella storia dopo i 90 s di attesa (alle 10:06 UTC il Ledger rispondeva in 208-217 s): la
   ricetta restava sul Ledger senza annuncio (405). Attesa reale portata a 420 s, come il consultorio.
3. `world` nella storia dopo i 6 s di attesa: il GP non prescriveva e aspettava il push (60-90 s o mai).

Uso: python tools/test_gp_attese.py
"""
import asyncio
import importlib.util
import os
import sys

from city_sdk.city import LEDGER, CapError, Message

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("tfix", os.path.join(REPO, "tools", "test_fix.py"))
tfix = importlib.util.module_from_spec(spec)
sys.argv = [sys.argv[0]]
src = open(spec.origin, encoding="utf-8").read().replace("asyncio.run(main())", "pass")
exec(compile(src, spec.origin, "exec"), tfix.__dict__)

FAILS = []


def check(name, cond, h=None):
    print(("  PASS " if cond else "  FAIL ") + name)
    if not cond:
        FAILS.append(name)
        if h:
            h.dump()


def gp():
    h = tfix.harness("gp", tfix.GP, role_card="gp")
    h.mod._PULL_PAUSE = 0
    return h


async def turn(h, text):
    try:
        await h.turn(tfix.CIT, text)
        return False
    except Exception:  # noqa: BLE001 - e' proprio il crash che la prova esclude
        return True


def failing_history(h, fails):
    original = h.port.history
    left = {"n": fails}

    async def history(*, peer=None, need_id=None):
        if left["n"] > 0:
            left["n"] -= 1
            raise CapError("UPSTREAM_TIMEOUT", "history")
        return await original(peer=peer, need_id=need_id)

    h.port.history = history


def late_ledger(h, head, after_reads):
    """La risposta del Ledger a `head` compare nella storia dopo `after_reads` letture; nessun push."""
    world = h.world
    answer = world.answer
    held = {}
    world.answer = lambda text: None if text.startswith(head) else answer(text)
    post, history = h.port.post, h.port.history
    reads = {"n": 0}

    async def posted(*, to, message_type, body, need_id, conversation_id, traceparent):
        if to == LEDGER and body.get("text", "").startswith(head):
            held[head] = answer(body["text"])
        return await post(to=to, message_type=message_type, body=body, need_id=need_id,
                          conversation_id=conversation_id, traceparent=traceparent)

    async def late(*, peer=None, need_id=None):
        if held.get(head):
            reads["n"] += 1
            if reads["n"] == after_reads:
                h.port.log.append(Message(type="chat", sender=LEDGER, recipient=h.me, msg_id=f"late-{head}",
                                          need_id=h.need, conversation_id="c-1", body={"text": held[head]}))
        return await history(peer=peer, need_id=need_id)

    h.port.post, h.port.history = posted, late


async def main():
    print("GP - history in 504 all'inizio del turno")
    h = gp()
    failing_history(h, 1)
    crashed = await turn(h, "Ho mal di schiena da settimane")
    check("un 504 e poi la storia: nessun crash, ricetta del protocollo",
          not crashed and len(h.out(tfix.CIT, "prescription")) == 1, h)
    h = gp()
    failing_history(h, 99)
    crashed = await turn(h, "Ho un forte dolore al petto")
    check("storia sempre in errore e red flag: nessun crash, escalation al cittadino",
          not crashed and len(h.out(tfix.CIT, "escalate.emergency")) == 1, h)
    h = gp()
    failing_history(h, 99)
    crashed = await turn(h, "Ho mal di schiena da settimane")
    check("storia sempre in errore senza red flag: nessun crash, nessuna ricetta alla cieca",
          not crashed and not h.out(LEDGER, "prescribe"), h)

    print("GP - attese del Ledger")
    import importlib
    real = importlib.util.spec_from_file_location("gp_real", os.path.join(REPO, "asst", "gp", "agent", "agent.py"))
    mod = importlib.util.module_from_spec(real)
    real.loader.exec_module(mod)
    check("valore vero: _RX_WAIT >= 420 s", getattr(mod, "_RX_WAIT", 0) >= 420)
    check("valore vero: _WORLD_WAIT >= 180 s", getattr(mod, "_WORLD_WAIT", 0) >= 180)

    h = gp()
    h.mod._WORLD_WAIT, h.mod._WORLD_STEP = 5.0, 0.0
    h.mod._GP_WORLD_CACHE.clear() if hasattr(h.mod, "_GP_WORLD_CACHE") else None
    late_ledger(h, "world", after_reads=40)
    await turn(h, "Ho mal di schiena da settimane")
    check("world nella storia dopo 40 letture (oltre i 6 s): ricetta nello stesso turno",
          len(h.out(LEDGER, "prescribe")) == 1, h)

    print("FALLITE:", FAILS if FAILS else "nessuna")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    asyncio.run(main())
