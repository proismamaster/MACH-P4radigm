"""Specialist answers need.request from other ASSTs' booking centres (level-4 common format).

Uso: python tools/test_specialist_ricerca.py
"""
import asyncio
import importlib.util
import os
import sys

from city_sdk.city import LEDGER, Message

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("spec", os.path.join(REPO, "asst", "specialist", "agent", "agent.py"))
mod = importlib.util.module_from_spec(spec)
sys.modules["spec"] = mod
spec.loader.exec_module(mod)
mod._PULL_PAUSE = 0

ME = "agent:sh35cbsy287d"
CUP = "agent:altra/cup"
FAILS = []


def check(name, cond):
    print(("  PASS " if cond else "  FAIL ") + name)
    if not cond:
        FAILS.append(name)


def slot(sid, doctor, at, **extra):
    more = " ".join(f"{k}={v}" for k, v in extra.items())
    return f"slot_id={sid} doctor_id={doctor} facility={ME} procedure=VIS-CARD at={at} {more}".strip()


# Agenda: martedì 17/11 08:00 UTC. Finestra B: fino a giovedì 19/11 08:00.
SLOTS = "\n".join([
    "slots procedure=VIS-CARD page=1/1",
    slot("S-TUE", "asst-bicocca-s2", "2026-11-17T14:30:00Z"),            # s2, f, it
    slot("S-WED", "asst-bicocca-s1", "2026-11-18T10:30:00Z"),            # s1, m, it/en
    slot("S-RES", "asst-bicocca-s1", "2026-11-18T09:00:00Z", urgent_reserve="true"),
    slot("S-LATE", "asst-bicocca-s1", "2026-11-20T10:30:00Z"),           # fuori finestra B
])


class FakeCity:
    agent_id = ME

    def __init__(self):
        self.sent = []

    async def say(self, to, text, **_):
        self.sent.append((to, text))
        return f"m{len(self.sent)}"

    async def history(self, need_id=None):
        return [
            Message(type="chat", sender=LEDGER, recipient=ME, msg_id="l1", need_id="N-X",
                    body={"text": "agenda agenda_now=2026-11-17T08:00:00Z"}),
            Message(type="chat", sender=LEDGER, recipient=ME, msg_id="l2", need_id="N-X", body={"text": SLOTS}),
        ]


def search(text, rid):
    city = FakeCity()
    msg = Message(type="chat", sender=CUP, recipient=ME, msg_id="q-" + rid, need_id="N-X",
                  body={"text": f"{text} request_id={rid}"})
    asyncio.run(mod._facility(city, msg, [msg], reports=True, hold_self=False))
    return [t for to, t in city.sent if to == CUP]


print("Specialist - ricerca dai CUP delle altre ASST")
out = search("need.request service_type=specialist_care.cardiology procedure=VIS-CARD priority=B", "r1")
check("risponde con un solo messaggio", len(out) == 1)
body = out[0] if out else ""
check("offre i due slot nella finestra B, non la riserva U né quello tardi",
      "slot_id=S-TUE" in body and "slot_id=S-WED" in body and "S-RES" not in body and "S-LATE" not in body)
check("ogni riga ripete request_id e dice lingua e genere del medico",
      all("request_id=r1" in line and "doctor_lang=" in line and "doctor_gender=" in line for line in body.splitlines()))
out = search("need.request service_type=specialist_care.cardiology procedure=VIS-CARD priority=B lang=en", "r2")
check("lang=en: solo s1", out and "S-WED" in out[0] and "S-TUE" not in out[0])
out = search("need.request service_type=specialist_care.cardiology procedure=VIS-CARD priority=B lang=ka", "r3")
check("lingua che non parliamo: cancel no_availability", out and out[0].startswith("cancel reason=no_availability request_id=r3"))
out = search("need.request service_type=hospital.physiatry procedure=VIS-FIS priority=B", "r4")
check("servizio non nostro: procedure_not_offered", out and "reason=procedure_not_offered" in out[0])
city = FakeCity()
msg = Message(type="chat", sender=CUP, recipient=ME, msg_id="dup", need_id="N-X",
              body={"text": "need.request procedure=VIS-CARD priority=B request_id=r1"})
asyncio.run(mod._facility(city, msg, [msg], reports=True, hold_self=False))
check("stessa request_id: nessuna seconda risposta", not [t for to, t in city.sent if to == CUP])

print("FALLITE:", FAILS if FAILS else "nessuna")
sys.exit(1 if FAILS else 0)
