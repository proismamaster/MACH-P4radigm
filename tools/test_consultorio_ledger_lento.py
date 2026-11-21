"""Consultorio con il Ledger lento: NO_CAPACITY, EXPIRED, STALE_FENCE e attesa della risposta.

Uso, dalla cartella della repo: python tools/test_consultorio_ledger_lento.py
Riusa il City finto e il Ledger finto di tools/test_facility.py (senza modificarlo).

Console 21/11 07:30-08:50 UTC (percorsi 2560005, 3290003, 3200003, 2710004, 2660004):
- cinque cittadini ricevono le stesse quattro offerte (15/12 10:30, 12:00, 14:30, 16:00: sono gli unici slot
  validi della pagina 1); il primo che conferma tiene lo slot, gli altri ricevono
  `refused hold code=NO_CAPACITY` dopo ~100 s;
- il `cancel reason=NO_CAPACITY` e le offerte sostitutive citano di nuovo lo slot rifiutato (il cancel
  appena mandato non e' ancora nella cronologia): il cittadino lo riconferma e resta senza risposta;
- 30 commit su 36 finiscono in `refused commit code=STALE_FENCE detail=the fence expired`: il commit parte
  60-90 s dopo `held` (il push della risposta del Ledger arriva in ritardo) e un hold dura circa 2 minuti;
  i commit partiti entro 10 s da `held` sono andati tutti a buon fine;
- `refused hold code=EXPIRED detail=slot ... has passed`: lo slot e' passato, una riprova non puo' riuscire.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

# MACH_FC_AGENT prova lo stesso scenario su un'altra versione del file (es. quella di main).
AGENT_FILE = os.environ.get("MACH_FC_AGENT") or os.path.join(REPO, "asst", "family_counseling", "agent", "agent.py")
sys.argv = [sys.argv[0], AGENT_FILE]  # test_facility legge l'agente da argv
import test_facility as tf  # noqa: E402

tf.AGENT_FILE = AGENT_FILE
CAP, ME, PROC, DOC = "family_counseling.gynecology", "agent:t02/family_counseling", "CONS-GIN", "asst-bicocca-c1"

# I percorsi della console e i loro cittadini.
N_A, CIT_A = "N-2026-11-02-8909110002560005", "citizen:W01QQQ-11-0005-000256"
N_B, CIT_B = "N-2026-11-02-8909110003290003", "citizen:W01QQQ-11-0003-000329"
N_C, CIT_C = "N-2026-11-02-8909110003200003", "citizen:W01QQQ-11-0003-000320"
HELLO = "Buongiorno, mi dicono che e' un attimo e si attendono secoli. Ho l'impegnativa e vorrei fissare una visita."
check = tf.check


def sid(day: str, hhmm: str) -> str:
    return f"W01QQQ-asst-bicocca-c1-{day}-{hhmm}"


def slot(day: str, hhmm: str, dow: str, reserve: bool = False) -> str:
    """Una riga del mondo vero (/v1/team/world): uno slot del consultorio `asst-bicocca-c1`."""
    when = f"{day[:4]}-{day[4:6]}-{day[6:]}T{hhmm[:2]}:{hhmm[2:]}:00.000Z"
    line = f"slot_id={sid(day, hhmm)} procedure={PROC} facility={ME} doctor_id={DOC} at={when} day={dow} free=1"
    return line + (" urgent_reserve=true" if reserve else "")


# Lunedi' 14/12 18:00 d'agenda. Pagina 1: i cinque slot del 14 (gia' passati) e quelli del 15, come nella
# console (09:00 e' la riserva urgente: restano quattro slot validi). Pagina 2: il 16.
PAGE1 = [slot("20261214", h, "mon", h == "0900") for h in ("0900", "1030", "1200", "1430", "1600")] + \
        [slot("20261215", h, "tue", h == "0900") for h in ("0900", "1030", "1200", "1430", "1600")]
PAGE2 = [slot("20261216", h, "wed", h == "0900") for h in ("0900", "1030", "1200", "1430", "1600")]
S1030, S1200, S1430, S1600 = (sid("20261215", h) for h in ("1030", "1200", "1430", "1600"))


class Ledger(tf.World):
    """Il Ledger della console: un hold su uno slot gia' tenuto e' NO_CAPACITY, su uno slot passato e'
    EXPIRED, un commit con la fence scaduta e' STALE_FENCE."""

    def __init__(self, now="2026-12-14T18:00:35.254Z"):
        super().__init__(ME, {f"{PROC}:1": tf.slots_reply(ME, PAGE1, "1/2"),
                              f"{PROC}:2": tf.slots_reply(ME, PAGE2, "2/2")})
        self.now = now
        self.held: dict[str, str] = {}      # slot -> hold_id
        self.booked: set[str] = set()
        self.past: set[str] = set()
        self.stale = 0                      # i prossimi `stale` commit trovano la fence scaduta
        self.hold_calls: list[str] = []

    def answer(self, text):
        words = text.split()
        f = dict(w.split("=", 1) for w in words[1:] if "=" in w)
        if words[0] == "agenda":
            return f"agenda wave_id=W01QQQ rate=60.0 paused=false agenda_now={self.now} agenda_day=mon"
        if words[0] == "hold":
            s = f["slot_id"]
            self.hold_calls.append(s)
            if s in self.past:
                return f"refused hold code=EXPIRED detail=slot {s} has passed"
            if s in self.held or s in self.booked:
                return f"refused hold code=NO_CAPACITY detail={s}"
            self.n += 1
            self.held[s] = f"bk-{self.n}"
            return (f"held hold_id=bk-{self.n} fence=1 slot_id={s} need_id=N. "
                    f"Next: commit hold_id=bk-{self.n} consent_ref=<ref>")
        if words[0] == "commit":
            hold = f["hold_id"]
            slot_of = next((s for s, h in self.held.items() if h == hold), "")
            self.held.pop(slot_of, None)
            if self.stale > 0:
                self.stale -= 1
                return "refused commit code=STALE_FENCE detail=the fence expired"
            self.booked.add(slot_of)
            return f"committed ledger_ref=LR-{hold} booking_id={hold} slot_id={slot_of}"
        return super().answer(text)


def offered(h: tf.Harness, citizen: str) -> list[str]:
    """Gli slot offerti al cittadino, nell'ordine: tutte le offerte di un giro stanno in UN messaggio."""
    return [line.split("slot_id=")[1].split()[0] for text in h.out(citizen, "offer")
            for line in text.splitlines() if line.startswith("offer ")]


def batches(h: tf.Harness, citizen: str) -> int:
    return len(h.out(citizen, "offer"))


def cancels(h: tf.Harness, citizen: str) -> list[str]:
    return h.out(citizen, "cancel")


def make(**kw) -> tf.Harness:
    h = tf.Harness(CAP, ME, Ledger(**kw), need=N_A)
    h.mod._WAIT_SECONDS = 0.0  # il Ledger di tf.Harness risponde al turno dopo: niente attese
    return h


async def open_case(h: tf.Harness, need: str, citizen: str) -> list[str]:
    h.need = need
    before = len(offered(h, citizen))
    await h.turn(citizen, HELLO)
    return offered(h, citizen)[before:]


async def confirm(h: tf.Harness, need: str, citizen: str, slot_id: str) -> None:
    h.need = need
    await h.turn(citizen, f"confirm consent_ref=cons-{need}-booking offer_id=of-{slot_id}")


# --- 1. NO_CAPACITY: i due percorsi della console ----------------------------------------------------------


async def no_capacity() -> None:
    print("NO_CAPACITY: 2560005 e 3290003 (le stesse quattro offerte, uno slot solo)")
    h = make()
    a = await open_case(h, N_A, CIT_A)
    b = await open_case(h, N_B, CIT_B)
    check("ogni cittadino riceve tre offerte in un solo messaggio (prima: un secondo giro a ogni push del Ledger)",
          len(a) == 3 and len(b) == 3 and batches(h, CIT_A) == 1 and batches(h, CIT_B) == 1, h)
    check("B riceve per prima uno slot che ad A non e' stato offerto (prima: le stesse quattro nello stesso ordine)",
          b[0] not in a and a[0] == S1030, h)

    # La contesa vera: lo slot a[0] e' gia' tenuto da un altro cittadino (2710004) che questo processo non vede.
    h = make()
    a = await open_case(h, N_A, CIT_A)
    h.world.held[a[0]] = "bk-altro"
    await confirm(h, N_A, CIT_A, a[0])
    cs = cancels(h, CIT_A)
    check("A conferma lo slot gia' tenuto: un cancel NO_CAPACITY con offer_id e slot_id",
          len(cs) == 1 and "reason=NO_CAPACITY" in cs[0] and f"offer_id=of-{a[0]}" in cs[0]
          and f"slot_id={a[0]}" in cs[0], h)
    again = offered(h, CIT_A)[len(a):]
    check("le offerte sostitutive non citano lo slot rifiutato (prima: era la prima della lista)",
          a[0] not in again and bool(again) and len(again) <= 3, h)
    check("... non ripetono uno slot e non portano slot gia' tenuti dal Ledger",
          len(again) == len(set(again)) and not set(again) & set(h.world.held), h)
    check("un solo hold sul Ledger: NO_CAPACITY non si riprova", len(h.out(tf.LEDGER, "hold")) == 1, h)

    # Il cittadino riconferma lo slot rifiutato (come 07:41:28, 07:57:29, 08:13:31): mai silenzio, mai un secondo hold.
    spoken = len(cancels(h, CIT_A)) + len(offered(h, CIT_A))
    await confirm(h, N_A, CIT_A, a[0])
    check("riconferma dello slot rifiutato: nessun secondo hold", len(h.out(tf.LEDGER, "hold")) == 1, h)
    check("... una risposta (il cancel o le offerte), non il silenzio",
          len(cancels(h, CIT_A)) + len(offered(h, CIT_A)) > spoken, h)
    check("... che non rimette in offerta lo slot rifiutato", a[0] not in offered(h, CIT_A)[len(a):], h)

    # 3290003: lo stesso, sul secondo cittadino dello stesso mondo.
    b = await open_case(h, N_B, CIT_B)
    h.world.held[b[0]] = "bk-altro2"
    await confirm(h, N_B, CIT_B, b[0])
    again_b = offered(h, CIT_B)[len(b):]
    check("3290003: stesso esito, lo slot rifiutato non torna",
          b[0] not in again_b and bool(again_b) and any("reason=NO_CAPACITY" in t for t in cancels(h, CIT_B)), h)


async def non_si_tiene_cio_che_e_di_un_altro() -> None:
    print("Slot tenuto da un altro caso di questo processo: niente hold che il Ledger rifiuterebbe dopo 100 s")
    h = make()
    a = await open_case(h, N_A, CIT_A)
    await open_case(h, N_C, CIT_C)
    h.need = N_C
    await h.turn(CIT_C, f"confirm consent_ref=cons-{N_C}-booking offer_id=of-{a[0]}")
    check("C tiene a[0]: un hold e la prenotazione", h.world.hold_calls == [a[0]] and a[0] in h.world.booked, h)
    await confirm(h, N_A, CIT_A, a[0])
    check("A conferma lo stesso slot: nessun hold in piu' (il consultorio sa che e' preso)",
          h.world.hold_calls == [a[0]], h)
    check("... risposta subito: cancel NO_CAPACITY e offerte sostitutive senza quello slot",
          any("reason=NO_CAPACITY" in t for t in cancels(h, CIT_A)) and a[0] not in offered(h, CIT_A)[len(a):], h)


# --- 2. EXPIRED sull'hold: lo slot e' passato, niente riprova -------------------------------------------


async def expired_sull_hold() -> None:
    print("EXPIRED sull'hold (slot passato): un hold, un cancel, offerte senza quello slot")
    h = make()
    a = await open_case(h, N_A, CIT_A)
    h.world.past.add(a[0])
    await confirm(h, N_A, CIT_A, a[0])
    check("un solo hold: la riprova non puo' riuscire su uno slot passato", len(h.out(tf.LEDGER, "hold")) == 1, h)
    cs = cancels(h, CIT_A)
    check("un solo cancel al cittadino, con offer_id e slot_id",
          len(cs) == 1 and "reason=EXPIRED" in cs[0] and f"slot_id={a[0]}" in cs[0], h)
    again = offered(h, CIT_A)[len(a):]
    check("offerte sostitutive: ci sono, senza lo slot passato, senza doppioni",
          bool(again) and a[0] not in again and len(again) == len(set(again)), h)
    b = await open_case(h, N_B, CIT_B)
    check("lo slot passato non va a un altro cittadino", a[0] not in b, h)


# --- 3. STALE_FENCE sul commit: una riprova, poi il cancel; mai doppioni ------------------------------


def redeliver(h: tf.Harness, message: tf.Message):
    """Lo stesso messaggio (stesso msg_id) consegnato di nuovo: il push dopo il poll."""
    city = tf.City(index=tf.Index(), messages=h.port, history=h.port, agent_id=ME, inbound=message)
    return h.mod.main(tf.Need(summary=message.text, message=message), city)


async def stale_fence() -> None:
    print("STALE_FENCE sul commit: una riprova, recupero senza doppioni")
    h = make()
    h.world.stale = 1
    a = await open_case(h, N_A, CIT_A)
    await confirm(h, N_A, CIT_A, a[0])
    check("una volta: due hold e due commit sullo stesso slot", len(h.out(tf.LEDGER, "hold")) == 2
          and len(h.out(tf.LEDGER, "commit")) == 2 and h.world.hold_calls == [a[0], a[0]], h)
    check("una sola ricevuta, nessun cancel, nessuna offerta in piu'",
          len(h.out(CIT_A, "booking.receipt")) == 1 and not cancels(h, CIT_A) and len(offered(h, CIT_A)) == len(a), h)

    h = make()
    h.world.stale = 99
    a = await open_case(h, N_A, CIT_A)
    await confirm(h, N_A, CIT_A, a[0])
    check("sempre STALE_FENCE: due hold e due commit, non di piu'",
          len(h.out(tf.LEDGER, "hold")) == 2 and len(h.out(tf.LEDGER, "commit")) == 2, h)
    cs = cancels(h, CIT_A)
    check("... un solo cancel con lo slot e nessuna ricevuta",
          len(cs) == 1 and f"slot_id={a[0]}" in cs[0] and not h.out(CIT_A, "booking.receipt"), h)
    again = offered(h, CIT_A)[len(a):]
    check("... e offerte sostitutive senza quello slot e senza doppioni",
          bool(again) and a[0] not in again and len(again) == len(set(again)), h)

    # Lo stesso rifiuto consegnato di nuovo (poll e push): ne' una riprova ne' un cancel in piu'.
    holds, cancel_n, offer_n = len(h.out(tf.LEDGER, "hold")), len(cancels(h, CIT_A)), len(offered(h, CIT_A))
    for row in [r for r in h.port.log if r.sender == tf.LEDGER and r.text.startswith("refused commit")]:
        await redeliver(h, row)
    check("lo stesso rifiuto consegnato di nuovo: nessun hold, cancel o offerta in piu'",
          len(h.out(tf.LEDGER, "hold")) == holds and len(cancels(h, CIT_A)) == cancel_n
          and len(offered(h, CIT_A)) == offer_n, h)


# --- 4. Attesa della risposta: il commit parte subito dopo `held` -----------------------------------------


class Arena(tf.Harness):
    """Il Ledger come in Arena: la risposta compare nella cronologia del caso solo dopo `reads` letture e il push
    che apre il turno arriva dopo il turno che ha chiesto (nella console 40-90 s dopo)."""

    def __init__(self, world, reads=4, need=N_A):
        super().__init__(CAP, ME, world, need=need)
        self.reads, self.n_reads, self.queue = reads, 0, []
        self.snapshot: list[tf.Message] = []
        real_post, real_history = self.port.post, self.port.history

        async def post(*, to, message_type, body, need_id, conversation_id, traceparent):
            mid = await real_post(to=to, message_type=message_type, body=body, need_id=need_id,
                                  conversation_id=conversation_id, traceparent=traceparent)
            if to == tf.LEDGER:
                reply = self.world.answer(body["text"])
                if reply is not None:
                    msg = tf.Message(type="chat", sender=tf.LEDGER, recipient=ME, msg_id=tf.uuid4().hex,
                                     need_id=need_id, conversation_id="c-ledger", body={"text": reply},
                                     sent_at=datetime.now(timezone.utc).isoformat())
                    self.queue.append([self.n_reads + self.reads, msg, False])
            return mid

        async def history(*, peer=None, need_id=None):
            self.n_reads += 1
            have = {r.msg_id for r in self.port.log}
            for due, msg, _ in self.queue:
                if due <= self.n_reads and msg.msg_id not in have:
                    self.port.log.append(msg)
            return await real_history(peer=peer, need_id=need_id)

        self.port.post, self.port.history = post, history
        self.mod._WAIT_SECONDS, self.mod._WAIT_STEP = 2.0, 0.0

    async def run_one(self, msg: tf.Message) -> None:
        city = tf.City(index=tf.Index(), messages=self.port, history=self.port, agent_id=ME, inbound=msg)
        await self.mod.main(tf.Need(summary=msg.text, message=msg), city)

    async def turn(self, sender, text, mtype="chat"):
        msg = tf.Message(type=mtype, sender=sender, recipient=ME, msg_id=tf.uuid4().hex, need_id=self.need,
                         conversation_id="c-1", body={"text": text})
        self.port.log.append(msg)
        await self.run_one(msg)
        self.snapshot = list(self.port.log)  # com'e' il caso quando il turno finisce, prima dei push
        while True:
            nxt = next((q for q in self.queue if not q[2]), None)
            if nxt is None:
                return
            nxt[2] = True
            if nxt[1].msg_id not in {r.msg_id for r in self.port.log}:
                self.port.log.append(nxt[1])
            await self.run_one(nxt[1])

    def before_push(self, to: str, word: str) -> list[str]:
        """I messaggi di tipo `word` mandati a `to` dentro il turno, prima che arrivi un push."""
        return [r.text for r in self.snapshot if r.sender == ME and r.recipient.startswith(to)
                and r.text.split()[0] == word]

    def offers_before_push(self, citizen: str) -> int:
        return sum(1 for text in self.before_push(citizen, "offer") for line in text.splitlines()
                   if line.startswith("offer "))


async def attesa_della_risposta() -> None:
    print("Ledger lento: il turno aspetta la risposta nella cronologia e va avanti subito")
    h = Arena(Ledger(), reads=4)
    await h.turn(CIT_A, HELLO)
    check("prima offerta: agenda e world arrivano dopo 4 letture, le tre offerte partono nello stesso turno",
          h.offers_before_push(CIT_A) == 3 and len(h.before_push(CIT_A, "offer")) == 1, h)
    check("... e i push che arrivano dopo non aggiungono altre offerte",
          len(offered(h, CIT_A)) == 3 and batches(h, CIT_A) == 1, h)

    a = offered(h, CIT_A)
    await h.turn(CIT_A, f"confirm consent_ref=cons-{N_A}-booking offer_id=of-{a[0]}")
    check("hold: `held` arriva dopo 4 letture, il commit parte nello stesso turno del confirm",
          len(h.before_push(tf.LEDGER, "hold")) == 1 and len(h.before_push(tf.LEDGER, "commit")) == 1, h)
    check("... e la ricevuta parte nello stesso turno, appena `committed` e' nella cronologia",
          len(h.before_push(CIT_A, "booking.receipt")) == 1, h)
    check("i push di held e committed (in ritardo) non fanno un secondo commit ne' una seconda ricevuta",
          len(h.out(tf.LEDGER, "commit")) == 1 and len(h.out(CIT_A, "booking.receipt")) == 1
          and len(h.out(tf.LEDGER, "hold")) == 1, h)

    # STALE_FENCE col Ledger lento: la riprova usa la stessa attesa.
    h = Arena(Ledger(), reads=3)
    h.world.stale = 1
    await h.turn(CIT_A, HELLO)
    a = offered(h, CIT_A)
    await h.turn(CIT_A, f"confirm consent_ref=cons-{N_A}-booking offer_id=of-{a[0]}")
    check("STALE_FENCE col Ledger lento: due hold, due commit, una ricevuta nello stesso turno, nessun cancel",
          len(h.out(tf.LEDGER, "hold")) == 2 and len(h.out(tf.LEDGER, "commit")) == 2
          and len(h.before_push(CIT_A, "booking.receipt")) == 1 and not cancels(h, CIT_A), h)

    # Il Ledger non risponde entro l'attesa: il turno finisce, il push riprende il lavoro.
    h = Arena(Ledger(), reads=10 ** 6)
    h.mod._WAIT_SECONDS = 0.05
    await h.turn(CIT_A, HELLO)
    check("attesa finita senza risposta: nessuna offerta nel turno, poi i push portano le tre offerte",
          not h.before_push(CIT_A, "offer") and len(offered(h, CIT_A)) == 3, h)


# --- 5. Due cittadini, un solo Ledger -----------------------------------------------------------------------


async def due_cittadini() -> None:
    print("Due cittadini, un solo Ledger: nessuno slot offerto per primo a tutti e due")
    h = Arena(Ledger(), reads=2)
    await open_case(h, N_A, CIT_A)
    await open_case(h, N_B, CIT_B)
    a, b = offered(h, CIT_A), offered(h, CIT_B)
    check("tre offerte a testa e prima scelta diversa", len(a) == 3 and len(b) == 3 and a[0] != b[0], h)
    await confirm(h, N_A, CIT_A, a[0])
    await confirm(h, N_B, CIT_B, b[0])
    check("tutti e due prenotati: due ricevute, nessun cancel",
          len(h.out(CIT_A, "booking.receipt")) == 1 and len(h.out(CIT_B, "booking.receipt")) == 1
          and not cancels(h, CIT_A) and not cancels(h, CIT_B), h)
    await open_case(h, N_C, CIT_C)
    c = offered(h, CIT_C)
    check("un terzo cittadino non riceve gli slot gia' prenotati", bool(c) and not set(c) & {a[0], b[0]}, h)


# --- 6. I CUP partner: gli slot presi non si offrono, un confirm su uno slot preso riceve subito il cancel ----

CUP = "agent:t01/booking_centre"  # un'altra ASST rispetto al consultorio (t02)
SEARCH = "need.request service_type=family_counseling.gynecology procedure=CONS-GIN priority=D request_id={r}"
CUP_CONFIRM = ("confirm offer_id=of-{s} slot_id={s} citizen=citizen:t01/c-9 consent_ref=cons-9 "
               "cross_asst_consent_ref=cons-x request_id={r}")


async def ricerche_dei_cup() -> None:
    print("CUP partner: slot preso da un cittadino, ricerca e confirm")
    h = make()
    a = await open_case(h, N_A, CIT_A)
    await confirm(h, N_A, CIT_A, a[0])
    check("A prenotato su a[0]", a[0] in h.world.booked, h)
    h.need = "N-CUP-1"
    await h.turn(CUP, SEARCH.format(r="rq-1"))
    lines = [line for t in h.out(CUP, "offer") for line in t.splitlines() if line.startswith("offer ")]
    slots = [line.split("slot_id=")[1].split()[0] for line in lines]
    check("la ricerca di un CUP non riceve lo slot gia' prenotato", bool(slots) and a[0] not in slots and len(slots) <= 3, h)

    h.need = "N-CUP-2"
    holds = len(h.out(tf.LEDGER, "hold"))
    await h.turn(CUP, CUP_CONFIRM.format(s=a[0], r="rq-2"))
    cs = h.out(CUP, "cancel")
    check("un confirm del CUP su uno slot gia' preso: nessun hold e subito un cancel no_capacity con offer_id",
          len(h.out(tf.LEDGER, "hold")) == holds and len(cs) == 1 and "reason=no_capacity" in cs[0]
          and f"offer_id=of-{a[0]}" in cs[0] and f"slot_id={a[0]}" in cs[0], h)
    await h.turn(CUP, CUP_CONFIRM.format(s=a[0], r="rq-2"))
    check("... lo stesso confirm di nuovo non fa un secondo cancel", len(h.out(CUP, "cancel")) == 1, h)


def segni() -> None:
    print("Slot non liberi: scadenza e proprietario dei segni")
    h = make()
    mod, clock = h.mod, [1000.0]
    mod.monotonic = lambda: clock[0]
    mod._mark_gone("S-held", "held", "N-X")
    mod._mark_gone("S-full", "full")
    mod._mark_gone("S-past", "past", "N-X")
    mod._mark_gone("S-booked", "booked", "N-X")
    check("tutti i segni valgono per gli altri casi", mod._gone() == {"S-held", "S-full", "S-past", "S-booked"})
    check("il caso che tiene lo slot non vede come 'preso' il proprio hold ne' la propria prenotazione",
          mod._gone(besides="N-X") == {"S-full", "S-past"})
    clock[0] += 151
    check("dopo 151 s tenuto e pieno scadono (l'hold dura circa due minuti), passato e prenotato restano",
          mod._gone() == {"S-past", "S-booked"})
    mod._mark_gone("S-held", "held", "N-X")
    mod._release("S-held", "N-Y")
    check("il rilascio vale solo per il caso che teneva lo slot", "S-held" in mod._gone())
    mod._release("S-held", "N-X")
    check("... e libera lo slot", "S-held" not in mod._gone())
    mod._release("S-booked", "N-X")
    check("uno slot prenotato non si libera", "S-booked" in mod._gone())


async def run() -> None:
    await no_capacity()
    await non_si_tiene_cio_che_e_di_un_altro()
    await expired_sull_hold()
    await stale_fence()
    await attesa_della_risposta()
    await due_cittadini()
    await ricerche_dei_cup()
    segni()
    print(f"\n{'TUTTO OK' if not tf.FAILS else str(len(tf.FAILS)) + ' FALLITE'}")
    sys.exit(1 if tf.FAILS else 0)


if __name__ == "__main__":
    asyncio.run(run())
