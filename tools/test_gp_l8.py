"""GP, livello 8: red flag scritte in altro modo e world lento.

Uso, dalla cartella della repo: python tools/test_gp_l8.py
- Le red flag del protocollo (dolore al petto, perdita di forza alle gambe) arrivano anche parafrasate.
- Una red flag del world vale anche con altre parole (due terzi delle parole, in qualsiasi ordine).
- Il GP aspetta il world 6 secondi (prima 2: il 201 restava senza risposta) e non prescrive mai senza
  averlo letto, perche' il livello 8 nasconde li' le red flag.
- Nessuna falsa emergenza sui testi normali della console.
"""

import asyncio
import importlib.util
import os
import sys

from city_sdk.city import Message

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("gp", os.path.join(REPO, "asst", "gp", "agent", "agent.py"))
gp = importlib.util.module_from_spec(spec)
sys.modules["gp"] = gp
spec.loader.exec_module(gp)
FAILS = []


def check(name, cond):
    print(("  PASS " if cond else "  FAIL ") + name)
    if not cond:
        FAILS.append(name)


def msg(text):
    return Message(type="chat", sender="citizen:t/c-1", recipient="agent:t/gp", msg_id="m", need_id="N-1",
                   body={"text": text})


print("Red flag parafrasate")
for text in ("Ho una fitta al petto da stamattina.", "Mi fa male il petto, dolore toracico forte.",
             "Da ieri non sento più le gambe quando cammino.", "I have pain in my chest since this morning.",
             "My legs feel weak and I keep falling."):
    check(f"emergenza: {text}", gp._emergency(msg(text)))
for text in ("Ho male al ginocchio quando cammino.", "Sento il cuore che batte forte, vorrei un controllo.",
             "Mal di schiena da settimane, vorrei una visita.", "yo, lowkey got back pain fr",
             "Il ginocchio mi fa dannare e ho solo alcuni giorni disponibili."):
    check(f"nessuna emergenza: {text}", not gp._emergency(msg(text)))

print("Red flag del world con altre parole")
check("'perdita di forza alle gambe' ~ 'ho perso forza nelle gambe'",
      gp._flag_in("perdita di forza alle gambe", "ho perso forza nelle gambe da ieri"))
check("'dolore al petto' ~ 'un dolore forte al petto'", gp._flag_in("dolore al petto", "ho un dolore forte al petto"))
check("nessun falso positivo: 'mal di schiena e gambe'", not gp._flag_in("perdita di forza alle gambe",
                                                                        "mal di schiena che scende nelle gambe"))


class SilentLedger:
    agent_id = "agent:t/gp"

    async def history(self, need_id=None):
        return []

    async def say(self, to, text):
        return "x"


print("World lento")
gp._PULL_PAUSE = 0.0
got = asyncio.run(gp._gp_select_protocol(SilentLedger(), msg("ginocchio"), [], "citizen:t/c-1", "SYM-KNEE", None))
check("senza world il GP non prescrive (red flag nascoste nel world)", got is None)

print("FALLITE:", FAILS if FAILS else "nessuna")
sys.exit(1 if FAILS else 0)
