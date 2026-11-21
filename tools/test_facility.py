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

from city_sdk.city import LEDGER, City, Message, Need, Peer

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
    """city.find: i centri prenotazioni dei test (t01, t02, t09), come li darebbe l'Index vero."""

    async def search(self, query):
        return [Peer(agent_id=f"agent:{t}/booking_centre", role="booking_centre",
                     capabilities=("booking_centre",)) for t in ("t01", "t02", "t09")]


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
    again = h.out(CUP_EXT, "offer")
    check("L7 ritrasmissione: stessa request_id = stesse offerte, parola per parola",
          len(again) == 2 and again[1] == again[0], h)
    h.world.slots["VIS-FIS:1"] = slots_reply(HOSP, ROWS[3:4])  # il Ledger cambia nel frattempo
    await h.turn(CUP_EXT, SEARCH)
    again = h.out(CUP_EXT, "offer")
    check("L7 ritrasmissione dopo un cambio del Ledger: ancora le stesse offerte",
          len(again) == 3 and again[2] == again[0], h)

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
    receipts = h.out(CUP_OWN, "booking.receipt")
    check("L7 confirm duplicato: nessun secondo hold/commit, stessa ricevuta parola per parola",
          len(h.out(LEDGER, "hold")) == 1 and len(h.out(LEDGER, "commit")) == 1
          and len(receipts) == 2 and receipts[1] == receipts[0], h)

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
        check(f"L8 rifiuto {op} del Ledger: cancel al CUP con reason={code.lower()}, nessuna ricevuta",
              len(cancels) == 1 and f"reason={code.lower()}" in cancels[0].split()
              and "offer_id=of-x-1" in cancels[0] and not h.out(CUP_OWN, "booking.receipt"), h)


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


class LiveWorld(World):
    """Ledger come in Arena: un secondo commit sullo stesso hold e' rifiutato."""

    def __init__(self, me: str, duplicate: str = "refused commit hold_id={h} code=DUPLICATE") -> None:
        super().__init__(me)
        self.committed: set[str] = set()
        self.duplicate = duplicate

    def answer(self, text: str) -> str | None:
        words = text.split()
        f = dict(w.split("=", 1) for w in words[1:] if "=" in w)
        if words[0] == "commit":
            hold = f["hold_id"]
            if hold in self.committed:
                return self.duplicate.format(h=hold)
            self.committed.add(hold)
        return super().answer(text)


class LivePort(Port):
    """Mailbox come in Arena: la risposta del Ledger e' subito nella cronologia del caso
    e apre anche un turno suo, in parallelo. La cronologia arriva con un po' di ritardo,
    quindi due turni leggono il caso prima che le scritture dell'altro ci siano."""

    def __init__(self, me: str, harness: "LiveHarness") -> None:
        super().__init__(me)
        self.harness = harness

    async def post(self, *, to, message_type, body, need_id, conversation_id, traceparent):
        mid = await super().post(to=to, message_type=message_type, body=body, need_id=need_id,
                                 conversation_id=conversation_id, traceparent=traceparent)
        if to == LEDGER:
            reply = self.harness.world.answer(body.get("text", ""))
            if reply is not None:
                self.harness.spawn(LEDGER, reply, conversation="c-ledger")
        return mid

    async def history(self, *, peer=None, need_id=None):
        rows = [r for r in self.log if need_id is None or r.need_id == need_id]
        await asyncio.sleep(0.02)
        return rows


class LiveHarness(Harness):
    def __init__(self, cap: str, me: str, world: World) -> None:
        super().__init__(cap, me, world)
        self.port = LivePort(me, self)
        self.mod._PULL_PAUSE = 0.01
        self.tasks: list[asyncio.Task] = []

    def spawn(self, sender: str, text: str, conversation: str = "c-1") -> None:
        msg = Message(type="chat", sender=sender, recipient=self.me, msg_id=uuid4().hex,
                      need_id=self.need, conversation_id=conversation, body={"text": text})
        self.port.log.append(msg)
        city = City(index=Index(), messages=self.port, history=self.port, agent_id=self.me,
                    inbound=msg)
        self.tasks.append(asyncio.ensure_future(self.mod.main(Need(summary=text, message=msg), city)))

    async def settle(self) -> None:
        while any(not t.done() for t in self.tasks):
            await asyncio.gather(*[t for t in self.tasks if not t.done()])


async def prova_d() -> None:
    print("Prova D - doppio commit (percorsi 069 e 099): turno del confirm e turno di held")
    for label, duplicate in (
        ("DUPLICATE", "refused commit hold_id={h} code=DUPLICATE"),
        ("rifiuto senza codice", "refused commit hold_id={h}"),
    ):
        h = LiveHarness("hospital.physiatry", HOSP, LiveWorld(HOSP, duplicate))
        h.spawn(CUP_OWN, CONFIRM)
        await h.settle()
        check(f"[{label}] un solo commit per hold", len(h.out(LEDGER, "commit")) == 1, h)
        check(f"[{label}] una sola ricevuta al CUP", len(h.out(CUP_OWN, "booking.receipt")) == 1, h)
        check(f"[{label}] nessun cancel al CUP dopo la ricevuta", not h.out(CUP_OWN, "cancel"), h)

    h = LiveHarness("hospital.physiatry", HOSP, LiveWorld(HOSP))
    h.spawn(CUP_OWN, CONFIRM)
    h.spawn(CUP_OWN, CONFIRM)  # stessa busta consegnata due volte, due turni in parallelo
    await h.settle()
    check("confirm doppio in parallelo: un solo hold e un solo commit",
          len(h.out(LEDGER, "hold")) == 1 and len(h.out(LEDGER, "commit")) == 1, h)
    check("confirm doppio in parallelo: una ricevuta, nessun cancel",
          len(h.out(CUP_OWN, "booking.receipt")) == 1 and not h.out(CUP_OWN, "cancel"), h)

    # Dopo una ricevuta valida un DUPLICATE tardivo del Ledger non annulla la prenotazione.
    h = Harness("hospital.physiatry", HOSP, World(HOSP))
    await h.turn(CUP_OWN, CONFIRM)
    await h.turn(LEDGER, "refused commit hold_id=H-1 code=DUPLICATE")
    await h.turn(LEDGER, "refused commit hold_id=H-1")
    check("rifiuto tardivo dopo la ricevuta: nessun cancel",
          len(h.out(CUP_OWN, "booking.receipt")) == 1 and not h.out(CUP_OWN, "cancel"), h)


async def prova_e() -> None:
    """Le prove della conformance della città (city_conform, nel Python di city-cli).

    Il mittente delle prove è un agente (`agent:t05/osp-x`) che esiste solo nella suite. Ogni
    messaggio che l'ospedale gli manda è contato come effetto: se arriva durante la richiesta
    dopo dà `invoke.signature: effect` o `invoke.idempotency: conflict effect`, e il brain che
    aspetta la consegna fa scadere i 5 s di `custody.ack` (renews=[] acks=[])."""

    print("Prova E - prove della conformance (custody.ack, invoke.idempotency, invoke.signature)")
    try:
        from city_conform.world import good_agent
    except ImportError:
        print("  SKIP city_conform non installato: usa il Python di city-cli")
        return
    import time
    os.environ["CITY_CARD"] = os.path.join(os.path.dirname(os.path.dirname(AGENT_FILE)), "card.yaml")
    spec = importlib.util.spec_from_file_location(f"agent_{uuid4().hex}", AGENT_FILE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    agent = await good_agent(brain=mod.main, role="facility")
    probes = (
        ("need generica (custody.ack, invoke.idempotency)", {"service": "lab", "summary": "visit", "district": 8}),
        ("need senza distretto (invoke.signature, terminal)", {"service": "lab", "summary": "visit"}),
        ("emergenza (invoke.semantics)", {"service": "lab", "summary": "alarm", "is_emergency": True, "district": 8}),
    )
    for label, body in probes:
        msg_id = str(uuid4())
        before = len(agent.sent_log())
        started = time.perf_counter()
        await agent.request("POST", "/invoke", agent.need(body=body, msg_id=msg_id))
        while (msg_id, 1) not in agent.renew_log() and time.perf_counter() - started < 8:
            await asyncio.sleep(0.01)
        elapsed = time.perf_counter() - started
        sent = [(to, b.get("text", "")) for to, b, _ in agent.sent_log()[before:] if to != LEDGER]
        check(f"{label}: nessun messaggio al mittente della prova (effetto)", not sent)
        if sent:
            print(f"        inviato: {sent}")
        check(f"{label}: brain finito e lease rinnovato entro 2 s ({elapsed:.2f} s)", elapsed < 2)
    await agent.stop()

    # Ledger lento (1 s per lettura della cronologia): un messaggio generico da un agente
    # sconosciuto non deve tenere il turno aperto.
    class SlowPort(Port):
        async def history(self, *, peer=None, need_id=None):
            await asyncio.sleep(1.0)
            return await super().history(peer=peer, need_id=need_id)

    for label, text in (("chat generica", "ciao, siete aperti?"),
                        ("need.request senza criteri", "need.request summary=visit")):
        h = Harness("hospital.physiatry", HOSP, World(HOSP))
        h.port = SlowPort(HOSP)
        started = time.perf_counter()
        await asyncio.wait_for(h.turn("agent:t77/sconosciuto", text), timeout=30)
        elapsed = time.perf_counter() - started
        check(f"Ledger lento, {label} da agente sconosciuto: turno sotto i 3 s ({elapsed:.2f} s), "
              f"nessuna risposta", elapsed < 3 and not h.out("agent:t77"), h)


F_ROWS = [
    "slot_id=S-1 doctor_id=D-x1 facility=ME procedure=VIS-FIS at=2026-11-24T09:00:00+01:00 day=tue free=1",
    "slot_id=S-6 doctor_id=D-x2 facility=ME procedure=VIS-FIS at=2026-11-24T10:30:00+01:00 day=tue free=1",
    "slot_id=S-5 doctor_id=D-x1 facility=ME procedure=VIS-FIS at=2026-11-24T15:00:00+01:00 day=tue free=1",
    "slot_id=S-7 doctor_id=D-x1 facility=ME procedure=VIS-FIS at=2026-11-24T17:00:00+01:00 day=tue free=1",
    "slot_id=S-8 doctor_id=D-x2 facility=ME procedure=VIS-FIS at=2026-11-25T11:00:00+01:00 day=wed free=1",
]
F_CONFIRM = (f"confirm offer_id=of-S-1 slot_id=S-1 citizen={CIT} consent_ref=cons-F-booking "
             "cross_asst_consent_ref=cons-F-cross prescription_number=prescription_number-F-1 "
             f"request_id=rq-T1 facility={HOSP}")


def after_line(h: Harness, marker: str, to: str) -> list[str]:
    """I messaggi dell'ospedale a ``to`` scritti dopo la prima riga che inizia con ``marker``."""
    log = h.port.log
    start = next((i for i, r in enumerate(log) if r.text.startswith(marker)), len(log))
    return [r.text for r in log[start:] if r.sender == HOSP and r.recipient == to]


async def prova_f() -> None:
    print("Prova F - livello 6: prenotazione annullata, riprenotazione in un solo messaggio")
    for label, fault, booking in (
        ("fault.cancel", "fault.cancel booking_id=BK-H-1 reason=facility_cancelled", "BK-H-1"),
        ("hold scaduto", "hold.expired hold_id=H-1 reason=facility_cancelled", "H-1"),
    ):
        h = Harness("hospital.physiatry", HOSP, World(HOSP, {"VIS-FIS:1": slots_reply(HOSP, F_ROWS)}))
        await h.turn(CUP_EXT, SEARCH)
        await h.turn(CUP_EXT, F_CONFIRM)
        check(f"[{label}] prima della prova: ricevuta al CUP per S-1",
              any("slot_id=S-1" in t for t in h.out(CUP_EXT, "booking.receipt")), h)
        await h.turn(LEDGER, fault)
        out = after_line(h, fault.split()[0], CUP_EXT)
        first = out[0].splitlines()[0] if out else ""
        offers = [line for line in out[0].splitlines()[1:]] if out else []
        check(f"[{label}] un solo messaggio a chi ha prenotato (il CUP)", len(out) == 1, h)
        check(f"[{label}] prima riga: cancel reason=facility_cancelled booking_id={booking}",
              first.split()[:1] == ["cancel"] and "reason=facility_cancelled" in first.split()
              and f"booking_id={booking}" in first.split(), h)
        slots = [dict(w.split("=", 1) for w in o.split()[1:] if "=" in w).get("slot_id") for o in offers]
        check(f"[{label}] sotto, fino a 3 offerte: prima lo stesso medico (S-5, S-7), poi S-6",
              all(o.startswith("offer ") for o in offers) and slots == ["S-5", "S-7", "S-6"], h)
        check(f"[{label}] offerte con request_id del CUP, mai lo slot annullato, nessun dato cittadino",
              all("request_id=rq-T1" in o.split() for o in offers)
              and "slot_id=S-1" not in " ".join(offers) and "citizen" not in " ".join(out), h)
        await h.turn(LEDGER, fault)
        check(f"[{label}] stesso annullo ripetuto: nessun secondo messaggio",
              len(after_line(h, fault.split()[0], CUP_EXT)) == 1, h)

    h = Harness("hospital.physiatry", HOSP, World(HOSP, {"VIS-FIS:1": slots_reply(HOSP, F_ROWS)}))
    await h.turn("agent:t77/sconosciuto", "fault.cancel booking_id=BK-H-1 reason=facility_cancelled")
    check("annullo da un agente qualsiasi (non Ledger, non citta'): ignorato", not h.out(""), h)


async def prova_g() -> None:
    print("Prova G - livello 8: codici del Ledger al CUP e regola P2 riletta sul confirm")
    for op, code, head, token in (("hold", "SLOT_UNKNOWN", "hold_refused", "ledger_code=SLOT_UNKNOWN"),
                                  ("commit", "RULE_VIOLATION", "hold_refused", "ledger_code=RULE_VIOLATION"),
                                  ("hold", "CONSENT_MISSING", "cancel", "reason=consent_missing")):
        h = Harness("hospital.physiatry", HOSP, World(HOSP, refuse={op: code}))
        await h.turn(CUP_OWN, CONFIRM)
        sent = h.out(CUP_OWN, head)
        other = h.out(CUP_OWN, "cancel" if head == "hold_refused" else "hold_refused")
        check(f"rifiuto {op} {code}: {head} ... {token}, offer_id e slot_id, nient'altro",
              len(sent) == 1 and token in sent[0].split() and "offer_id=of-x-1" in sent[0]
              and "slot_id=S-1" in sent[0] and not other and not h.out(CUP_OWN, "booking.receipt"), h)

    # P2 cambia a meta' partita: il confirm di un CUP esterno rilegge `rules` adesso.
    world = LiveWorld(HOSP)
    world.rules = "rules P2=on"
    h = LiveHarness("hospital.physiatry", HOSP, world)
    h.spawn(LEDGER, "rules none")  # lettura vecchia nella cronologia: P2 spenta
    await h.settle()
    h.spawn(CUP_EXT, f"confirm offer_id=of-a1-1 slot_id=S-1 citizen={CIT} consent_ref=cons-N-booking "
                     f"prescription_number=prescription_number-N-1 facility={HOSP}")
    await h.settle()
    check("P2 accesa adesso (rules vecchio diceva spenta): nessun hold senza consenso cross",
          not h.out(LEDGER, "hold"), h)
    check("P2 accesa: cancel reason=consent_missing al CUP esterno",
          any("reason=consent_missing" in t.split() for t in h.out(CUP_EXT, "cancel")), h)
    world.rules = "rules none"
    h.spawn(CUP_EXT, f"confirm offer_id=of-a1-2 slot_id=S-5 citizen={CIT} consent_ref=cons-N-booking "
                     f"prescription_number=prescription_number-N-1 facility={HOSP}")
    await h.settle()
    check("P2 spenta di nuovo: hold sullo slot confermato",
          any("slot_id=S-5" in t for t in h.out(LEDGER, "hold")), h)
async def prova_h() -> None:
    """custody.ack, la causa vera: le prove della conformance non hanno need_id.

    `city.history(need_id=None)` legge TUTTA la casella dell'agente (fino a 5 pagine da 200
    messaggi firmati, una dopo l'altra). La casella dell'ospedale ha ~1400 messaggi: il turno
    della prova dura secondi e la suite smette di aspettare il rinnovo del lease dopo 5 s."""

    print("Prova H - messaggio senza need_id: nessuna lettura dell'intera casella")
    import time

    class BigMailbox(Port):
        def __init__(self, me: str) -> None:
            super().__init__(me)
            self.whole_reads = 0

        async def history(self, *, peer=None, need_id=None):
            if need_id is None:
                self.whole_reads += 1
                await asyncio.sleep(3.0)  # come 5 pagine da 200 messaggi via Relay
            return await super().history(peer=peer, need_id=need_id)

    consultorio = "family_counseling" in os.path.normpath(AGENT_FILE).split(os.sep)
    cap, me = ("family_counseling.gynecology", FC) if consultorio else ("hospital.physiatry", HOSP)
    for label, body in (("prova della conformance (need.request lab/visit)", "need.request summary=visit"),
                        ("chat generica", "ciao")):
        h = Harness(cap, me, World(me))
        port = BigMailbox(me)
        h.port = port
        msg = Message(type="chat", sender="agent:t05/osp-x", recipient=me, msg_id=uuid4().hex,
                      need_id=None, conversation_id="c-1", body={"text": body})
        port.log.append(msg)
        city = City(index=Index(), messages=port, history=port, agent_id=me, inbound=msg)
        started = time.perf_counter()
        await h.mod.main(Need(summary=body, message=msg), city)
        elapsed = time.perf_counter() - started
        check(f"{label} senza need_id: nessuna lettura della casella intera, turno sotto 1 s "
              f"({elapsed:.2f} s, letture={port.whole_reads})",
              port.whole_reads == 0 and elapsed < 1 and not h.out(""), h)

    if consultorio:
        return  # con need_id il consultorio e' coperto dalla prova C
    # Un messaggio vero con need_id continua a funzionare (prova B lo copre per intero).
    h = Harness("hospital.physiatry", HOSP, World(HOSP))
    await h.turn(CUP_OWN, CONFIRM)
    check("con need_id: confirm -> hold, commit e ricevuta come prima",
          len(h.out(LEDGER, "hold")) == 1 and len(h.out(CUP_OWN, "booking.receipt")) == 1, h)


async def prova_i() -> None:
    """Scadenze in giorni di AGENDA (kit, ADR-124: sabato e domenica non esistono).

    Un CUP di un'altra ASST cerca fisiatria B di giovedi': la scadenza arriva a lunedi'. Con i
    giorni di calendario l'ospedale scartava ogni slot di lunedi' e rispondeva no_slots."""

    print("Prova I - scadenze in giorni di agenda (giovedi' + 2 = lunedi')")

    class Thursday(World):
        def answer(self, text: str) -> str | None:
            if text.split()[0] == "agenda":
                return "agenda agenda_now=2026-11-19T08:00:00+01:00"
            return super().answer(text)

    rows = [
        "slot_id=M-1 doctor_id=D-x1 facility=ME procedure=VIS-FIS at=2026-11-23T07:00:00+01:00 day=mon free=1",
        "slot_id=T-1 doctor_id=D-x1 facility=ME procedure=VIS-FIS at=2026-11-24T09:00:00+01:00 day=tue free=1",
    ]
    h = Harness("hospital.physiatry", HOSP, Thursday(HOSP, {"VIS-FIS:1": slots_reply(HOSP, rows)}))
    await h.turn(CUP_EXT, SEARCH)
    body = " ".join(h.out(CUP_EXT, "offer"))
    check("B di giovedi': offre lo slot di lunedi' (M-1), non quello di martedi' (T-1)",
          "slot_id=M-1" in body and "slot_id=T-1" not in body and not h.out(CUP_EXT, "cancel"), h)


async def prova_j() -> None:
    """P2 con gli ID veri della città, che non hanno la squadra (agent:<id>, non agent:<team>/<slug>).

    `_other_asst` cercava la squadra nell'id: con gli ID veri era sempre falso. Un CUP di un'altra
    ASST mandava `cross_asst_consent_ref` e l'ospedale lo ignorava (hold col consenso sbagliato,
    CONSENT_MISSING con P2 attiva); senza consenso cross e con P2 attiva l'ospedale faceva l'hold."""

    print("Prova J - P2 con gli ID veri (senza squadra nell'id)")
    me, ours, theirs = "agent:bb01ggxymm05", "agent:ez8cb7j167p2", "agent:h6r1v45esk77"
    base = (f"confirm offer_id=of-S-1 slot_id=S-1 citizen={CIT} consent_ref=cons-N-booking "
            f"prescription_number=prescription_number-N-1 facility={me}")

    h = Harness("hospital.physiatry", me, World(me))
    await h.turn(theirs, base + " cross_asst_consent_ref=cons-N-cross")
    holds = h.out(LEDGER, "hold")
    check("CUP di un'altra ASST con cross_asst_consent_ref: hold con il consenso cross",
          len(holds) == 1 and "consent_ref=cons-N-cross" in holds[0], h)

    h = Harness("hospital.physiatry", me, World(me, rules="rules P2=on"))
    await h.turn(LEDGER, "rules P2=on")
    await h.turn(theirs, base)
    check("P2 attiva, CUP di un'altra ASST senza consenso cross: nessun hold, cancel consent_missing",
          not h.out(LEDGER, "hold")
          and any("reason=consent_missing" in t.split() for t in h.out(theirs, "cancel")), h)

    h = Harness("hospital.physiatry", me, World(me, rules="rules P2=on"))
    await h.turn(LEDGER, "rules P2=on")
    await h.turn(ours, base)
    holds = h.out(LEDGER, "hold")
    check("P2 attiva, il NOSTRO CUP (stessa ASST): hold con il consenso di prenotazione",
          len(holds) == 1 and "consent_ref=cons-N-booking" in holds[0], h)


async def prova_k() -> None:
    """Il cittadino decide dopo 3-20 minuti reali = 3-27 ORE d'agenda (PROBLEMS, 04:25): uno slot a
    poche ore e' gia' passato quando conferma (EXPIRED, reason=past, 59 confirm su 61 senza ricevuta).
    Prima gli slot ad almeno 24 ore d'agenda, i vicini in coda; U (stesso giorno) come prima."""

    print("Prova K - prima gli slot ad almeno 24 ore d'agenda (il cittadino decide dopo ore)")
    rows = [
        "slot_id=N-1 doctor_id=D-x1 facility=ME procedure=VIS-FIS at=2026-11-23T13:00:00+01:00 day=mon free=1",
        "slot_id=N-2 doctor_id=D-x1 facility=ME procedure=VIS-FIS at=2026-11-23T16:00:00+01:00 day=mon free=1",
        "slot_id=F-1 doctor_id=D-x1 facility=ME procedure=VIS-FIS at=2026-11-24T10:00:00+01:00 day=tue free=1",
        "slot_id=F-2 doctor_id=D-x2 facility=ME procedure=VIS-FIS at=2026-11-24T15:00:00+01:00 day=tue free=1",
    ]
    # D (5 giorni): prima gli slot ad almeno 24 ore. B (scadenza dalla nascita del need, ~20 ore gia'
    # passate quando il CUP scrive): il piu' vicino prima, come chiede MACH-1.3.
    for priority, expected, label in (("D", ["F-1", "F-2", "N-1"], "D: prima martedi' (oltre 24 ore), poi il vicino N-1"),
                                      ("B", ["N-1", "N-2", "F-1"], "B: prima il piu' vicino (finestra corta)")):
        h = Harness("hospital.physiatry", HOSP, World(HOSP, {"VIS-FIS:1": slots_reply(HOSP, rows)}))
        await h.turn(CUP_EXT, SEARCH.replace("priority=B", f"priority={priority}").replace("rq-T1", f"rq-K{priority}"))
        offers = h.out(CUP_EXT, "offer")
        order = [w.split("=", 1)[1] for line in (offers[0].splitlines() if offers else [])
                 for w in line.split() if w.startswith("slot_id=")]
        check(f"lunedi' 08:00, {label}", order == expected, h)

    h = Harness("hospital.physiatry", HOSP, World(HOSP, {"VIS-FIS:1": slots_reply(HOSP, rows)}))
    await h.turn(CUP_EXT, SEARCH.replace("priority=B", "priority=U"))
    body = " ".join(h.out(CUP_EXT, "offer"))
    check("U (stesso giorno): offre gli slot di oggi come prima",
          "slot_id=N-1" in body and "slot_id=F-1" not in body, h)


async def run() -> None:
    # Ogni agente ha le sue prove: A, B, D, F, G e I provano l'ospedale, C il consultorio; E e H valgono per tutti.
    if "family_counseling" in os.path.normpath(AGENT_FILE).split(os.sep):
        await prova_c()
    else:
        await prova_a()
        await prova_b()
        await prova_d()
        await prova_f()
        await prova_g()
        await prova_i()
        await prova_j()
        await prova_k()
    await prova_e()
    await prova_h()
    print(f"\n{'TUTTO OK' if not FAILS else str(len(FAILS)) + ' FALLITE'}")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    asyncio.run(run())
