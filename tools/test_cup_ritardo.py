"""CUP con il Ledger lento (console 21/11 05:00-05:15: agenda, ricetta e world tornavano dopo 7-9 minuti).

Uso, dalla cartella della repo: python tools/test_cup_ritardo.py
- Agenda e pagine del catalogo lette per un cittadino servono agli altri della stessa ondata per 5 minuti.
- Senza letture condivise, il primo turno chiede insieme ricetta, agenda e pagina 1 (procedura dal service_type).
- Con letture condivise fresche chiede solo la ricetta e, appena arriva, offre senza altri giri.
- Un turno aperto dalla risposta di un partner non aspetta le altre risposte (prima: 6 letture per turno).
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from city_sdk.city import LEDGER, City, Message, Need

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_cup_l5_vincoli as base  # noqa: E402  (Ledger finto del test L5)

cup = base.cup
FAILS = []


def check(name, cond):
    print(("  PASS " if cond else "  FAIL ") + name)
    if not cond:
        FAILS.append(name)


NOW = datetime.now(timezone.utc).replace(microsecond=0)
STAMP = (NOW - timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
OLD = (NOW - timedelta(seconds=cup._SHARED_SECONDS + 60)).strftime("%Y-%m-%dT%H:%M:%SZ")
AGENDA_AT = "2026-11-23T08:00:00Z"
CIT_A, CIT_B, CIT_X = "citizen:W01QQQ-11-0001", "citizen:W01QQQ-11-0002", "citizen:W02ZZZ-11-0001"


def row(sender, text, need="N-A", sent_at=STAMP, msg_id=None):
    return Message(type="chat", sender=sender, recipient=base.AGENT, msg_id=msg_id or f"{need}-{abs(hash(text)) % 10**8}",
                   need_id=need, body={"text": text}, sent_at=sent_at)


def page(procedure, number, total, slot_id, when="2026-11-24T10:30:00.000Z", wave="W01QQQ"):
    return (f"slots wave_id={wave} asst=asst-bicocca page={number}/{total}\n"
            f"slot_id={slot_id} procedure={procedure} facility={base.HOSPITAL} doctor_id=asst-bicocca-s2 "
            f"at={when} day=tue free=1")


print("Letture condivise per ondata")
cup._SHARED.clear()
agenda = row(LEDGER, f"agenda wave_id=W01QQQ agenda_now={AGENDA_AT} paused=false agenda_day=mon")
card1 = row(LEDGER, page("VIS-CARD", 1, 2, "card-1"))
fis1 = row(LEDGER, page("VIS-FIS", 1, 1, "fis-1"))
chat_a = [row(CIT_A, "need.request service_type=specialist_care.cardiology"), agenda, card1, fis1]
cup._shared_reads(chat_a, CIT_A, "VIS-CARD")
chat_b = [row(CIT_B, "need.request service_type=specialist_care.cardiology", need="N-B")]
got = cup._shared_reads(chat_b, CIT_B, "VIS-CARD")
ids = {r.msg_id for r in got}
check("stessa ondata: arrivano agenda e pagina 1 di VIS-CARD", agenda.msg_id in ids and card1.msg_id in ids)
check("mai le pagine di un'altra procedura", fis1.msg_id not in ids)
check("le letture condivise stanno prima del caso (le sue vincono)", got[-1] is chat_b[-1])
check("senza procedura: solo l'agenda (controllo al confirm)",
      {r.msg_id for r in cup._shared_reads(chat_b, CIT_B, None)} - {chat_b[0].msg_id} == {agenda.msg_id})
check("un'altra ondata non riceve niente", cup._shared_reads([row(CIT_X, "x", need="N-X")], CIT_X, "VIS-CARD")[0].sender == CIT_X)
own = row(LEDGER, page("VIS-CARD", 1, 2, "card-own"), need="N-B")
got = cup._shared_reads([chat_b[0], own], CIT_B, "VIS-CARD")
check("il caso ha gia' la sua pagina 1: niente doppione", card1.msg_id not in {r.msg_id for r in got})
cup._SHARED.clear()
cup._shared_reads([row(CIT_A, "x"), row(LEDGER, f"agenda wave_id=W01QQQ agenda_now={AGENDA_AT}", sent_at=OLD)], CIT_A, None)
check("oltre 5 minuti non si usa", len(cup._shared_reads(chat_b, CIT_B, "VIS-CARD")) == 1)
cup._SHARED.clear()
cup._shared_reads([row(CIT_A, "x"), row(LEDGER, f"agenda wave_id=W01QQQ agenda_now={AGENDA_AT} paused=true")], CIT_A, None)
check("agenda in pausa: non condivisa", not cup._SHARED)

print("Primo turno")


class Ledger(base.Mailbox):
    """Ledger finto che non risponde subito: si vede cosa chiede il CUP nel primo turno."""

    def __init__(self, name, citizen):
        self.need_id = f"N-{name}"
        self.rows, self.sent, self.citizen, self.reads = [], [], citizen, 0

    async def history(self, *, peer, need_id):
        self.reads += 1
        return list(self.rows)

    async def run(self, text):
        inbound = Message(type="chat", sender=self.citizen, recipient=base.AGENT, msg_id=f"{self.need_id}-in",
                          need_id=self.need_id, body={"text": text}, sent_at=STAMP)
        self.rows.append(inbound)
        city = City(index=self, history=self, messages=self, agent_id=base.AGENT, inbound=inbound)
        with patch.dict(os.environ, {"CITY_ROLE": "booking_centre"}), patch.object(cup, "_CUP_RING", ()), \
                patch.object(cup, "_PULL_PAUSE", 0.0):
            await cup.main(Need(message=inbound), city)
        return [r.text for r in self.sent if r.recipient == LEDGER]


REQUEST = f"need.request prescription_number={base.RX} service_type=specialist_care.cardiology lang=it"
cup._SHARED.clear()
asked = asyncio.run(Ledger("cold", CIT_A).run(REQUEST))
check("niente di condiviso: ricetta, agenda e world VIS-CARD pagina 1 insieme",
      sorted(a.split()[0] for a in asked) == ["agenda", "prescription", "world"]
      and "world procedure=VIS-CARD page=1" in asked)

cup._shared_reads([row(CIT_A, "x"), agenda, row(LEDGER, page("VIS-CARD", 1, 1, "card-shared",
                                                            when="2026-11-24T10:30:00.000Z"))], CIT_A, "VIS-CARD")
warm = Ledger("warm", CIT_B)
asked = asyncio.run(warm.run(REQUEST))
check("con agenda e pagina 1 condivise chiede solo la ricetta", [a.split()[0] for a in asked] == ["prescription"])
warm.rows.append(Message(type="chat", sender=LEDGER, recipient=base.AGENT, msg_id="rx", need_id=warm.need_id,
                         body={"text": f"prescription prescription_number={base.RX} state=issued patient={CIT_B} "
                                       "procedure=VIS-CARD priority=D"}, sent_at=STAMP))
inbound = warm.rows[-1]
city = City(index=warm, history=warm, messages=warm, agent_id=base.AGENT, inbound=inbound)
with patch.dict(os.environ, {"CITY_ROLE": "booking_centre"}), patch.object(cup, "_CUP_RING", ()), \
        patch.object(cup, "_PULL_PAUSE", 0.0), patch.object(cup, "_agenda_now",
                                                            lambda chat, real_now=None: datetime(2026, 11, 23, 8, tzinfo=timezone.utc)
                                                            if any(r.sender == LEDGER and r.text.startswith("agenda") for r in chat) else None):
    asyncio.run(cup.main(Need(message=inbound), city))
offers = [o for r in warm.sent if r.recipient == CIT_B for o in cup._offer_blocks(r.text)]
check("arrivata la ricetta, offre lo slot condiviso senza altri giri di Ledger",
      [o["slot_id"] for o in offers] == ["card-shared"] and [r.text.split()[0] for r in warm.sent if r.recipient == LEDGER] == ["prescription"])

print("Turni dei partner")
import inspect  # noqa: E402
src = inspect.getsource(cup._cup_cross_asst)
check("solo il turno che manda le ricerche aspetta le risposte", "if started_here and searches.keys() - answered" in src)
check("al massimo 6 partner per ricerca", cup._CUP_MAX_PARTNERS == 6)

print("FALLITE:", FAILS if FAILS else "nessuna")
sys.exit(1 if FAILS else 0)
