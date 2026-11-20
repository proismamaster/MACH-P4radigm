"""Prove A, B, C per hospital e family_counseling con un City finto (Ledger al turno dopo).

Uso, dalla cartella della repo (serve il pacchetto city-sdk: pip install city-sdk):
    python tools/test_facility.py                       # prova asst/hospital/agent/agent.py
    python tools/test_facility.py asst/family_counseling/agent/agent.py
Il ruolo viene da una card temporanea, quindi lo stesso file viene provato come
ospedale e come consultorio. Non sostituisce `city run` ne la conformance di `city deploy`.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import tempfile
from uuid import uuid4

from city_sdk.city import LEDGER, City, Message, Need

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
AGENT_FILE = (sys.argv[1] if len(sys.argv) > 1
              else os.path.join(REPO, "asst", "hospital", "agent", "agent.py"))

CARD = """agent_id: {aid}
team: team:local-dev
name: x
role: facility
capabilities:
  - {cap}
no_clinical_advice: true
"""


def load(cap: str, aid: str):
    card = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
    card.write(CARD.format(aid=aid, cap=cap))
    card.close()
    os.environ["CITY_CARD"] = card.name
    os.environ.pop("CITY_ROLE", None)
    spec = importlib.util.spec_from_file_location(f"agent_{uuid4().hex}", AGENT_FILE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._PULL_TRIES = 1  # niente attese: le risposte del Ledger arrivano al turno successivo
    return mod


class Index:
    async def search(self, query):
        return []


class Port:
    def __init__(self, me: str) -> None:
        self.me = me
        self.log: list[Message] = []

    async def post(self, *, to, message_type, body, need_id, conversation_id, traceparent):
        mid = uuid4().hex
        self.log.append(Message(type=message_type, sender=self.me, recipient=to, msg_id=mid,
                                need_id=need_id, conversation_id=conversation_id, body=body))
        return mid

    async def history(self, *, peer=None, need_id=None):
        return [r for r in self.log if need_id is None or r.need_id == need_id]


AGENDA = "agenda agenda_now=2026-11-23T08:00:00+01:00"


def slots_reply(me: str, rows: list[str], page: str = "1/1") -> str:
    return "\n".join([f"slots page={page}", *[r.replace("ME", me) for r in rows]])


class World:
    """Ledger scriptabile: risponde a world/agenda/rules/hold/commit/checkin."""

    def __init__(self, me: str, slots: dict[str, str] | None = None, rules: str = "rules none",
                 refuse: dict[str, str] | None = None) -> None:
        self.me = me
        self.slots = slots or {}
        self.rules = rules
        self.refuse = refuse or {}
        self.n = 0

    def answer(self, text: str) -> str | None:
        words = text.split()
        op = words[0]
        f = dict(w.split("=", 1) for w in words[1:] if "=" in w)
        if op == "world":
            return self.slots.get(f"{f.get('procedure')}:{f.get('page', '1')}",
                                  "slots page=1/1")
        if op == "agenda":
            return AGENDA
        if op == "rules":
            return self.rules
        if op == "hold":
            if "hold" in self.refuse:
                return f"refused hold slot_id={f['slot_id']} code={self.refuse['hold']}"
            self.n += 1
            return f"held hold_id=H-{self.n} slot_id={f['slot_id']} fence=1"
        if op == "commit":
            if "commit" in self.refuse:
                return f"refused commit hold_id={f['hold_id']} code={self.refuse['commit']}"
            return f"committed booking_id=BK-{f['hold_id']} ledger_ref=LR-{f['hold_id']}"
        if op == "checkin":
            return f"checked_in booking_id={f['booking_id']} citizen={f.get('citizen', '')}"
        return None


class Harness:
    def __init__(self, cap: str, me: str, world: World, need: str = "N-2026-11-23-0001") -> None:
        self.mod = load(cap, me)
        self.me = me
        self.port = Port(me)
        self.world = world
        self.need = need

    async def turn(self, sender: str, text: str, mtype: str = "chat") -> None:
        msg = Message(type=mtype, sender=sender, recipient=self.me, msg_id=uuid4().hex,
                      need_id=self.need, conversation_id="c-1", body={"text": text})
        self.port.log.append(msg)
        before = len(self.port.log)
        city = City(index=Index(), messages=self.port, history=self.port, agent_id=self.me,
                    inbound=msg)
        await self.mod.main(Need(summary=text, message=msg), city)
        # Ledger: una risposta per ogni messaggio inviato al Ledger in questo turno.
        sent = [r for r in self.port.log[before:] if r.recipient == LEDGER]
        for row in sent:
            reply = self.world.answer(row.text)
            if reply is not None:
                await self.turn(LEDGER, reply)

    def out(self, to_prefix: str = "", word: str = "") -> list[str]:
        return [r.text for r in self.port.log
                if r.sender == self.me and r.recipient.startswith(to_prefix)
                and (not word or r.text.split()[0] == word)]

    def dump(self) -> None:
        for r in self.port.log:
            print(f"    {r.sender[-22:]:>22} > {r.recipient[-22:]:<22} {r.text!r}")


FAILS: list[str] = []


def check(name: str, cond: bool, h: Harness | None = None) -> None:
    print(("  PASS " if cond else "  FAIL ") + name)
    if not cond:
        FAILS.append(name)
        if h:
            h.dump()


HOSP = "agent:t02/hospital"
CUP_EXT = "agent:t01/booking_centre"
CUP_OWN = "agent:t02/booking_centre"
CIT = "citizen:t01/c-0042"

ROWS = [
    "slot_id=S-1 doctor_id=D-x1 facility=ME procedure=VIS-FIS at=2026-11-24T09:00:00+01:00 day=tue free=1",
    "slot_id=S-2 doctor_id=D-x1 facility=ME procedure=VIS-FIS at=2026-11-24T10:00:00+01:00 day=tue free=1 urgent_reserve=true",
    "slot_id=S-3 doctor_id=D-x2 facility=ME procedure=VIS-FIS at=2026-11-24T11:00:00+01:00 day=tue free=0",
    "slot_id=S-4 doctor_id=D-x2 facility=ME procedure=VIS-FIS at=2026-11-28T11:00:00+01:00 day=fri free=1",
    "slot_id=S-9 doctor_id=D-y1 facility=agent:t02/specialist procedure=VIS-FIS at=2026-11-24T09:30:00+01:00 day=tue free=1",
]

SEARCH = "need.request service_type=hospital.physiatry procedure=VIS-FIS priority=B request_id=rq-T1"


async def prova_a() -> None:
    print("Prova A - disponibilita cross-ASST (hospital)")
    h = Harness("hospital.physiatry", HOSP,
                World(HOSP, {"VIS-FIS:1": slots_reply(HOSP, ROWS)}))
    await h.turn(CUP_EXT, SEARCH)
    offers = h.out(CUP_EXT, "offer")
    check("una sola risposta offer al CUP", len(offers) == 1, h)
    body = offers[0] if offers else ""
    check("offre S-1, una riga per slot, con request_id",
          "slot_id=S-1" in body and "request_id=rq-T1" in body, h)
    check("esclude riserva U (S-2), pieno (S-3), oltre B (S-4), altra struttura (S-9)",
          all(f"slot_id={s}" not in body for s in ("S-2", "S-3", "S-4", "S-9")), h)
    check("nessun dato cittadino nella ricerca", "citizen" not in body, h)
    await h.turn(CUP_EXT, SEARCH)  # ritrasmissione dello stesso request_id
    check("ritrasmissione: nessuna seconda risposta", len(h.out(CUP_EXT, "offer")) == 1, h)

    h = Harness("hospital.physiatry", HOSP,
                World(HOSP, {"VIS-FIS:1": slots_reply(HOSP, ROWS[1:3])}))
    await h.turn(CUP_EXT, SEARCH)
    cancels = h.out(CUP_EXT, "cancel")
    check("senza slot idonei: cancel con motivo e request_id",
          len(cancels) == 1 and "request_id=rq-T1" in cancels[0] and "reason=reserved_u" in cancels[0], h)

    h = Harness("hospital.physiatry", HOSP,
                World(HOSP, {"VIS-FIS:1": slots_reply(HOSP, [ROWS[1].replace(
                    "2026-11-24T10:00", "2026-11-23T14:00")])}))
    await h.turn(CUP_EXT, SEARCH.replace("priority=B", "priority=U"))
    check("priorita U puo usare la riserva", "slot_id=S-2" in " ".join(h.out(CUP_EXT, "offer")), h)

    h = Harness("hospital.physiatry", HOSP, World(HOSP, {
        "VIS-FIS:1": slots_reply(HOSP, ROWS[2:3], "1/2"),
        "VIS-FIS:2": slots_reply(HOSP, ROWS[0:1], "2/2"),
    }))
    await h.turn(CUP_EXT, SEARCH)
    check("pagina 1 vuota: chiede la pagina 2 e offre S-1",
          "slot_id=S-1" in " ".join(h.out(CUP_EXT, "offer")), h)

    h = Harness("hospital.physiatry", HOSP, World(HOSP))
    await h.turn(CUP_EXT, SEARCH.replace("hospital.physiatry", "specialist_care.cardiology"))
    check("servizio sbagliato: cancel reason=wrong_service",
          any("reason=wrong_service" in t for t in h.out(CUP_EXT, "cancel")), h)

    # P2 attiva: confirm dal CUP di un'altra ASST senza consenso cross -> niente hold
    h = Harness("hospital.physiatry", HOSP,
                World(HOSP, {"VIS-FIS:1": slots_reply(HOSP, ROWS)}, rules="rules P2=on P3=on"))
    await h.turn(CUP_EXT, SEARCH)
    await h.turn(CUP_EXT, f"confirm offer_id=of-a1-1 slot_id=S-1 citizen={CIT} "
                          "consent_ref=cons-N-booking prescription_number=prescription_number-N-1 "
                          f"facility={HOSP}")
    check("P2 senza consenso cross: nessun hold", not h.out(LEDGER, "hold"), h)
    check("P2 senza consenso cross: cancel reason=consent_missing con offer_id del CUP",
          any("reason=consent_missing" in t and "offer_id=of-a1-1" in t
              for t in h.out(CUP_EXT, "cancel")), h)
    await h.turn(CUP_EXT, f"confirm offer_id=of-a1-1 slot_id=S-1 citizen={CIT} "
                          "consent_ref=cons-N-booking cross_consent_ref=cons-N-cross "
                          f"prescription_number=prescription_number-N-1 facility={HOSP}")
    holds = h.out(LEDGER, "hold")
    check("P2 con cross_consent_ref: hold con quel consenso",
          len(holds) == 1 and "consent_ref=cons-N-cross" in holds[0], h)
    check("P2: ricevuta dopo commit", len(h.out(CUP_EXT, "booking.receipt")) == 1, h)


CONFIRM = (f"confirm offer_id=of-x-1 slot_id=S-1 citizen={CIT} consent_ref=cons-T-booking "
           f"prescription_number=prescription_number-T-1 facility={HOSP}")


async def prova_b() -> None:
    print("Prova B - hold, commit, checkin, duplicato, rifiuto (hospital)")
    h = Harness("hospital.physiatry", HOSP, World(HOSP))
    await h.turn(CUP_OWN, CONFIRM)
    holds = h.out(LEDGER, "hold")
    commits = h.out(LEDGER, "commit")
    receipts = h.out(CUP_OWN, "booking.receipt")
    check("hold con slot, cittadino, ricetta, consenso",
          len(holds) == 1 and all(t in holds[0] for t in
                                  ("slot_id=S-1", f"citizen={CIT}", "consent_ref=cons-T-booking",
                                   "prescription_number=prescription_number-T-1")), h)
    check("commit sull'hold_id ricevuto", len(commits) == 1 and "hold_id=H-1" in commits[0], h)
    check("ricevuta al CUP solo dopo commit, con offer_id e slot_id del confirm",
          len(receipts) == 1 and all(t in receipts[0] for t in
                                     ("booking_id=BK-H-1", "ledger_ref=LR-H-1",
                                      "offer_id=of-x-1", "slot_id=S-1")), h)
    order = [r.text.split()[0] for r in h.port.log if r.sender == HOSP]
    check("ordine hold -> commit -> booking.receipt",
          order.index("hold") < order.index("commit") < order.index("booking.receipt"), h)

    await h.turn(CUP_OWN, CONFIRM)
    check("confirm duplicato: nessun secondo hold/commit/ricevuta",
          len(h.out(LEDGER, "hold")) == 1 and len(h.out(LEDGER, "commit")) == 1
          and len(h.out(CUP_OWN, "booking.receipt")) == 1, h)

    await h.turn(CIT, "checkin booking_id=BK-H-1 ledger_ref=LR-H-1")
    checkins = h.out(LEDGER, "checkin")
    to_cit = h.out(CIT, "checkin")
    check("checkin scritto sul Ledger con booking_id e cittadino",
          len(checkins) == 1 and "booking_id=BK-H-1" in checkins[0] and f"citizen={CIT}" in checkins[0], h)
    check("esito checkin al cittadino con ledger_ref",
          len(to_cit) == 1 and "ledger_ref=LR-H-1" in to_cit[0], h)

    for op, code in (("hold", "NO_CAPACITY"), ("commit", "PRESCRIPTION_EXPIRED")):
        h = Harness("hospital.physiatry", HOSP, World(HOSP, refuse={op: code}))
        await h.turn(CUP_OWN, CONFIRM)
        cancels = h.out(CUP_OWN, "cancel")
        check(f"rifiuto {op} del Ledger: cancel al CUP con motivo {code}, nessuna ricevuta",
              len(cancels) == 1 and f"reason={code}" in cancels[0] and "offer_id=of-x-1" in cancels[0]
              and not h.out(CUP_OWN, "booking.receipt"), h)


FC = "agent:t02/family_counseling"
CIT2 = "citizen:t02/c-0100"
FC_ROWS = [
    "slot_id=C-1 doctor_id=D-zz9 facility=ME procedure=CONS-GIN at=2026-11-24T09:00:00+01:00 day=tue free=1",
]


async def prova_c() -> None:
    print("Prova C - consultorio ad accesso diretto")
    h = Harness("family_counseling.gynecology", FC,
                World(FC, {"CONS-GIN:1": slots_reply(FC, FC_ROWS)}))
    await h.turn(CIT2, "vorrei una visita ginecologica")
    offers = h.out(CIT2, "offer")
    check("nessuna richiesta di ricetta o di dati",
          not h.out(CIT2, "data.request") and not h.out(LEDGER, "prescription"), h)
    check("offre C-1 (medico fuori dalla tabella _DOCTORS) senza prescription_number",
          any("slot_id=C-1" in t for t in offers) and not any("prescription_number" in t for t in offers), h)
    oid = next((t.split("offer_id=")[1].split()[0] for t in offers if "slot_id=C-1" in t), "of-C-1")
    await h.turn(CIT2, f"confirm offer_id={oid} consent_ref=cons-N-booking")
    holds = h.out(LEDGER, "hold")
    receipts = h.out(CIT2, "booking.receipt")
    check("hold su C-1 senza ricetta", len(holds) == 1 and "slot_id=C-1" in holds[0]
          and "prescription_number" not in holds[0], h)
    check("commit e ricevuta al cittadino legate a C-1",
          len(h.out(LEDGER, "commit")) == 1 and len(receipts) == 1 and "slot_id=C-1" in receipts[0], h)
    booking = receipts[0].split("booking_id=")[1].split()[0] if receipts else "BK-H-1"
    await h.turn(CIT2, f"checkin booking_id={booking}")
    check("checkin sul Ledger e al cittadino con lo stesso booking_id",
          any(f"booking_id={booking}" in t for t in h.out(LEDGER, "checkin"))
          and any(f"booking_id={booking}" in t for t in h.out(CIT2, "checkin")), h)

    h = Harness("family_counseling.gynecology", FC,
                World(FC, {"CONS-GIN:1": slots_reply(FC, FC_ROWS)}, refuse={"hold": "NO_CAPACITY"}))
    await h.turn(CIT2, "vorrei una visita ginecologica")
    await h.turn(CIT2, "confirm offer_id=of-C-1 consent_ref=cons-N-booking")
    check("consultorio: rifiuto hold -> cancel al cittadino con motivo",
          any("reason=NO_CAPACITY" in t for t in h.out(CIT2, "cancel")), h)

    h = Harness("family_counseling.gynecology", FC,
                World(FC, {"CONS-GIN:1": slots_reply(FC, FC_ROWS)}))
    await h.turn(CUP_EXT, "need.request service_type=family_counseling.gynecology "
                          "procedure=CONS-GIN priority=D request_id=rq-F1")
    check("consultorio risponde alla ricerca di un CUP esterno",
          any("slot_id=C-1" in t and "request_id=rq-F1" in t for t in h.out(CUP_EXT, "offer")), h)
    check("ricerca esterna: nessuna offerta diretta a cittadini", not h.out("citizen:", "offer"), h)


async def run() -> None:
    await prova_a()
    await prova_b()
    await prova_c()
    print(f"\n{'TUTTO OK' if not FAILS else str(len(FAILS)) + ' FALLITE'}")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    asyncio.run(run())
