"""MACH-1.2 lato struttura: criteri estesi, offerte rilassate, wheelchair.

Uso, dalla cartella della repo (serve city-sdk):
    python tools/test_mach12_struttura.py                                  # consultorio
    python tools/test_mach12_struttura.py asst/hospital/agent/agent.py     # ospedale

Riusa il City finto e il Ledger finto di tools/test_facility.py (senza modificarlo).
Gli slot hanno il formato di /v1/team/world (agenda_date, agenda_day, capacity, urgent_reserve).

Assunzioni (da confermare con MACH-1.2.md):
- need.request porta lang=, gender_preference=m|f, days=tue/thu, after=HH:MM, before=HH:MM,
  wheelchair=true. after e before sono l'ora locale dello slot: after <= ora < before.
- Insieme vuoto: UN messaggio. Prima riga `cancel reason=no_availability request_id=...`,
  poi al massimo 3 righe `offer ... relaxed=<criterio>`. Ogni slot rilassato viola esattamente
  quel criterio e rispetta tutti gli altri, finestra della priorità compresa.
- Criteri che si rilassano: days, after, before, gender_preference. La lingua NON si rilassa
  (come nel CUP: un medico che non parla la lingua del cittadino non è un'alternativa).
- wheelchair=true: il consultorio non è accessibile nel registry. Ogni slot viola il vincolo,
  e su quel vincolo non si rilassa: cancel no_availability senza offerte. L'ospedale è accessibile.
"""

from __future__ import annotations

import asyncio
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

AGENT_FILE = (sys.argv[1] if len(sys.argv) > 1
              else os.path.join(REPO, "asst", "family_counseling", "agent", "agent.py"))
ROLE = "hospital" if "hospital" in os.path.normpath(AGENT_FILE).split(os.sep) else "family_counseling"

sys.argv = [sys.argv[0], AGENT_FILE]  # test_facility legge l'agente da argv
import test_facility as tf  # noqa: E402

tf.AGENT_FILE = AGENT_FILE

if ROLE == "family_counseling":
    CAP, ME, PROC, DOC = ("family_counseling.gynecology", "agent:t02/family_counseling",
                          "CONS-GIN", "asst-bicocca-c1")
    ACCESSIBLE = False
else:
    CAP, ME, PROC, DOC = ("hospital.physiatry", "agent:t02/hospital", "VIS-FIS",
                          "asst-bicocca-h1")
    ACCESSIBLE = True

CUP = "agent:t01/booking_centre"
RELAXABLE = {"days", "after", "before", "gender_preference"}


def slot(slot_id: str, when: str, day: str, reserve: bool = False) -> str:
    """Una riga di slot nel formato di /v1/team/world."""
    line = (f"slot_id={slot_id} doctor_id={DOC} facility={ME} procedure={PROC} "
            f"agenda_date={when} agenda_day={day} capacity=1")
    return line + (" urgent_reserve=true" if reserve else "")


# Adesso: lunedì 23/11 ore 08:00 (Ledger finto). Priorità D = 5 giorni.
V1 = slot("V-1", "2026-11-24T11:00:00+01:00", "tue")             # rispetta tutto
X_DAYS = slot("X-days", "2026-11-25T11:00:00+01:00", "wed")      # solo il giorno
X_AFTER = slot("X-after", "2026-11-24T09:00:00+01:00", "tue")    # solo after
X_BEFORE = slot("X-before", "2026-11-26T14:00:00+01:00", "thu")  # solo before
X_TWO = slot("X-two", "2026-11-25T15:00:00+01:00", "wed")        # giorno e before: mai
X_LATE = slot("X-late", "2026-12-01T11:00:00+01:00", "tue")      # oltre la priorità D: mai
X_RES = slot("X-res", "2026-11-26T11:00:00+01:00", "thu", reserve=True)  # riserva U: mai
FAILS = {"X-days": "days", "X-after": "after", "X-before": "before"}

CRITERIA = "lang=en gender_preference=f days=tue/thu after=10:00 before=13:00"


def search(rid: str, extra: str = CRITERIA) -> str:
    return (f"need.request service_type={CAP} procedure={PROC} priority=D "
            f"request_id={rid} {extra}")


def harness(rows: list[str]) -> tf.Harness:
    return tf.Harness(CAP, ME, tf.World(ME, {f"{PROC}:1": tf.slots_reply(ME, rows)}))


def replies(h: tf.Harness) -> list[str]:
    return [r.text for r in h.port.log if r.sender == ME and r.recipient == CUP]


def lines_of(text: str, word: str) -> list[str]:
    return [line for line in text.splitlines() if line.split()[:1] == [word]]


def tokens(line: str) -> dict[str, str]:
    return dict(t.split("=", 1) for t in line.split() if "=" in t)


check = tf.check


async def criteri_estesi() -> None:
    print(f"Criteri estesi ({ROLE})")
    h = harness([V1, X_DAYS, X_AFTER, X_BEFORE, X_TWO, X_LATE, X_RES])
    await h.turn(CUP, search("rq-E1"))
    out = replies(h)
    offers = lines_of(out[0], "offer") if out else []
    check("una sola risposta al CUP", len(out) == 1, h)
    check("offre solo V-1, che rispetta lang, genere, giorni, after e before",
          [tokens(o).get("slot_id") for o in offers] == ["V-1"], h)
    check("offerta con request_id, doctor_lang/doctor_gender e senza relaxed=",
          bool(offers) and all("request_id=rq-E1" in o and "doctor_lang=" in o
                               and "doctor_gender=f" in o and "relaxed=" not in o
                               for o in offers), h)
    check("niente cancel quando c'e' uno slot valido",
          not any(lines_of(t, "cancel") for t in out), h)

    h = harness([V1])
    await h.turn(CUP, search("rq-E2", CRITERIA.replace("lang=en", "lang=de")))
    out = " ".join(replies(h))
    check("lingua non parlata (de): nessuna offerta valida e nessun relaxed=lang",
          "reason=no_availability" in out and "relaxed=lang" not in out
          and "relaxed=" not in out, h)

    if ACCESSIBLE:
        h = harness([V1])
        await h.turn(CUP, search("rq-E3", CRITERIA + " wheelchair=true"))
        out = replies(h)
        check("wheelchair=true in struttura accessibile: V-1 offerto",
              bool(out) and "slot_id=V-1" in out[0] and "relaxed=" not in out[0], h)


async def offerte_rilassate() -> None:
    print(f"Offerte rilassate ({ROLE})")
    h = harness([X_DAYS, X_AFTER, X_BEFORE, X_TWO, X_LATE, X_RES])
    await h.turn(CUP, search("rq-R1"))
    out = replies(h)
    check("un solo messaggio al CUP", len(out) == 1, h)
    text = out[0] if out else ""
    first = text.splitlines()[0] if text else ""
    check("prima riga: cancel reason=no_availability request_id=rq-R1",
          first.split()[:1] == ["cancel"] and "reason=no_availability" in first
          and "request_id=rq-R1" in first, h)
    offers = lines_of(text, "offer")
    check("sotto, da 1 a 3 righe offer", 1 <= len(offers) <= 3
          and len(text.splitlines()) == 1 + len(offers), h)
    ok = bool(offers)
    for line in offers:
        t = tokens(line)
        relaxed = t.get("relaxed", "")
        ok &= relaxed in RELAXABLE and FAILS.get(t.get("slot_id", "")) == relaxed
        ok &= t.get("request_id") == "rq-R1"
    check("ogni offerta rilassa un solo criterio, quello che lo slot viola", ok, h)
    check("mai slot con due criteri violati, oltre la priorita' o nella riserva U",
          not any(s in text for s in ("X-two", "X-late", "X-res")), h)

    h = harness([slot("G-1", "2026-11-24T11:00:00+01:00", "tue")])
    await h.turn(CUP, search("rq-R2", CRITERIA.replace("gender_preference=f",
                                                       "gender_preference=m")))
    out = replies(h)
    offers = lines_of(out[0], "offer") if out else []
    check("genere non disponibile (m): una riga offer con relaxed=gender_preference",
          len(offers) == 1 and tokens(offers[0]).get("relaxed") == "gender_preference", h)

    h = harness([X_TWO, X_LATE])
    await h.turn(CUP, search("rq-R3"))
    out = replies(h)
    text = out[0] if out else ""
    check("nessuna alternativa a un solo criterio: solo il cancel no_availability",
          len(out) == 1 and len(text.strip().splitlines()) == 1
          and len(lines_of(text, "cancel")) == 1
          and "reason=no_availability" in text and "no_slots" not in text, h)


async def sedia_a_rotelle() -> None:
    print(f"Wheelchair ({ROLE})")
    if ACCESSIBLE:
        print("  (struttura accessibile: coperto in Criteri estesi)")
        return
    h = harness([V1, X_DAYS, X_AFTER, X_BEFORE])
    await h.turn(CUP, search("rq-W1", CRITERIA + " wheelchair=true"))
    out = replies(h)
    text = out[0] if out else ""
    check("cancel reason=no_availability con request_id",
          any("reason=no_availability" in c and "request_id=rq-W1" in c
              for c in lines_of(text, "cancel")), h)
    check("nessuna offerta, neanche rilassata", not lines_of(text, "offer"), h)


# Righe vere del Ledger (team/PROBLEMS.md): agenda_date in UTC con millisecondi e "Z".
REAL = (f"slot_id=W01QQQ-asst-bicocca-c1-20261124-1030 capacity=1 facility={ME} doctor_id={DOC} "
        f"procedure={PROC} agenda_day=tue agenda_date=2026-11-24T09:30:00.000Z urgent_reserve=false")


async def righe_vere() -> None:
    print(f"Righe vere del Ledger ({ROLE})")
    h = harness([REAL])
    await h.turn(CUP, search("rq-V1", "after=10:00 before=11:00 days=tue"))
    out = replies(h)
    check("09:30Z sono le 10:30 a Milano: dentro after=10:00 before=11:00",
          bool(out) and "slot_id=W01QQQ-asst-bicocca-c1-20261124-1030" in out[0]
          and "relaxed=" not in out[0], h)
    if ROLE != "family_counseling":
        return
    cit = "citizen:t02/c-0200"
    h = harness([REAL])
    await h.turn(cit, "vorrei una visita ginecologica")
    offers = h.out(cit, "offer")
    check("accesso diretto: il cittadino riceve l'offerta con le righe vere",
          any("slot_id=W01QQQ-asst-bicocca-c1-20261124-1030" in o
              and "agenda_date=2026-11-24T09:30:00.000Z" in o for o in offers), h)


# --- Livello 6-7: riprenotazione dopo un annullo e idempotenza (solo consultorio) ---------------------
# Assunzioni (MACH-1.2, "REBOOK COMBO"; il formato del messaggio di annullo non e' nel kit):
# - Il Ledger o la citta' avvisa il consultorio con `fault.cancel booking_id=... reason=facility_cancelled`.
# - Chi aveva prenotato (cittadino o CUP) riceve UN solo messaggio: prima riga
#   `cancel reason=facility_cancelled booking_id=...`, sotto da 1 a 3 righe `offer`, prima quelle
#   con la stessa dottoressa. Mai lo slot annullato.
# - Stesso confirm = stessa ricevuta e mai un secondo hold. Stessa request_id = stesse offerte.
DOC2 = "asst-bicocca-c2"  # medico fuori dalla tabella: non viene scartato


def rslot(slot_id: str, doctor: str, when: str, day: str) -> str:
    return (f"slot_id={slot_id} capacity=1 facility={ME} doctor_id={doctor} procedure={PROC} "
            f"agenda_day={day} agenda_date={when} urgent_reserve=false")


R1 = rslot("R-1", DOC, "2026-11-25T09:30:00.000Z", "wed")    # quello prenotato e poi annullato
R2 = rslot("R-2", DOC, "2026-11-25T13:30:00.000Z", "wed")    # stessa dottoressa
R3 = rslot("R-3", DOC, "2026-11-26T09:30:00.000Z", "thu")    # stessa dottoressa
R4 = rslot("R-4", DOC2, "2026-11-26T14:00:00.000Z", "thu")   # altra dottoressa, la piu' presto
R5 = rslot("R-5", DOC2, "2026-11-27T09:00:00.000Z", "fri")   # altra dottoressa, fuori dal limite di 3
REBOOK_ROWS = [R1, R2, R3, R4, R5]
FAULT = "fault.cancel booking_id={b} reason=facility_cancelled"


def after_row(h: tf.Harness, marker: str, to: str) -> list[str]:
    """I messaggi del consultorio a `to` scritti dopo la riga `marker` (testo che inizia cosi')."""
    log = h.port.log
    start = next((i for i, r in enumerate(log) if r.text.startswith(marker)), len(log))
    return [r.text for r in log[start:] if r.sender == ME and r.recipient == to]


async def riprenota_cittadino() -> None:
    print("Riprenotazione dopo annullo: cittadino")
    cit = "citizen:t02/c-0300"
    h = harness(REBOOK_ROWS)
    await h.turn(cit, "vorrei una visita ginecologica")
    await h.turn(cit, "confirm offer_id=of-R-1 consent_ref=cons-N-booking")
    receipts = h.out(cit, "booking.receipt")
    check("prima della prova: prenotazione R-1 con ricevuta", len(receipts) == 1
          and "slot_id=R-1" in receipts[0], h)
    booking = tokens(receipts[0]).get("booking_id", "BK-H-1") if receipts else "BK-H-1"
    fault = FAULT.format(b=booking)
    await h.turn(tf.LEDGER, fault)
    out = after_row(h, "fault.cancel", cit)
    first = out[0].splitlines()[0] if out else ""
    check("un solo messaggio al cittadino dopo l'annullo", len(out) == 1, h)
    check("prima riga: cancel reason=facility_cancelled booking_id=...",
          first.split()[:1] == ["cancel"] and "reason=facility_cancelled" in first
          and f"booking_id={booking}" in first, h)
    offers = lines_of(out[0], "offer") if out else []
    check("sotto il cancel, da 1 a 3 offerte e nient'altro",
          1 <= len(offers) <= 3 and len(out[0].splitlines()) == 1 + len(offers), h)
    check("prima la stessa dottoressa (R-2, R-3), poi l'altra (R-4)",
          [tokens(o).get("slot_id") for o in offers] == ["R-2", "R-3", "R-4"], h)
    check("mai lo slot annullato R-1", "slot_id=R-1" not in " ".join(offers), h)
    check("ogni offerta ha offer_id, slot_id e agenda_date",
          bool(offers) and all({"offer_id", "slot_id", "agenda_date"} <= set(tokens(o))
                               for o in offers), h)
    await h.turn(tf.LEDGER, fault)
    check("stesso annullo ripetuto: nessun secondo messaggio",
          len(after_row(h, "fault.cancel", cit)) == 1, h)
    # Il cittadino sceglie l'ultima offerta del messaggio multiplo: il hold deve essere su R-4.
    await h.turn(cit, "confirm offer_id=of-R-4 consent_ref=cons-N-booking2")
    holds = h.out(tf.LEDGER, "hold")
    check("conferma dell'ultima offerta del messaggio multiplo: hold su R-4",
          len(holds) == 2 and "slot_id=R-4" in holds[-1], h)


async def riprenota_cup() -> None:
    print("Riprenotazione dopo annullo: CUP")
    h = harness(REBOOK_ROWS)
    await h.turn(CUP, search("rq-F1", ""))
    await h.turn(CUP, "confirm offer_id=of-R-1 slot_id=R-1 citizen=citizen:t01/c-9 "
                      "consent_ref=cons-1 request_id=rq-F1")
    receipts = h.out(CUP, "booking.receipt")
    check("prima della prova: ricevuta al CUP per R-1", len(receipts) == 1
          and "slot_id=R-1" in receipts[0], h)
    booking = tokens(receipts[0]).get("booking_id", "BK-H-1") if receipts else "BK-H-1"
    await h.turn(tf.LEDGER, FAULT.format(b=booking))
    out = after_row(h, "fault.cancel", CUP)
    first = out[0].splitlines()[0] if out else ""
    check("un solo messaggio al CUP dopo l'annullo", len(out) == 1, h)
    check("prima riga: cancel reason=facility_cancelled booking_id=...",
          first.split()[:1] == ["cancel"] and "reason=facility_cancelled" in first
          and f"booking_id={booking}" in first, h)
    offers = lines_of(out[0], "offer") if out else []
    check("offerte con request_id=rq-F1, prima la stessa dottoressa",
          [tokens(o).get("slot_id") for o in offers] == ["R-2", "R-3", "R-4"]
          and all(tokens(o).get("request_id") == "rq-F1" for o in offers), h)
    check("mai lo slot annullato R-1", "slot_id=R-1" not in " ".join(offers), h)
    check("nessun messaggio al cittadino: i suoi dati restano al CUP",
          not h.out("citizen:"), h)


async def idempotenza() -> None:
    print("Idempotenza (livello 7)")
    cit = "citizen:t02/c-0310"
    confirm = "confirm offer_id=of-R-1 consent_ref=cons-N-booking"
    h = harness(REBOOK_ROWS)
    await h.turn(cit, "vorrei una visita ginecologica")
    await h.turn(cit, confirm)
    await h.turn(cit, confirm)
    receipts = h.out(cit, "booking.receipt")
    check("stesso confirm due volte: un solo hold e un solo commit",
          len(h.out(tf.LEDGER, "hold")) == 1 and len(h.out(tf.LEDGER, "commit")) == 1, h)
    check("stesso confirm: la ricevuta e' sempre la stessa",
          bool(receipts) and len(set(receipts)) == 1, h)

    # La cronologia del Relay puo' non mostrare ancora il hold: il secondo confirm non lo ripete.
    h = harness(REBOOK_ROWS)
    await h.turn(cit, "vorrei una visita ginecologica")
    await h.turn(cit, confirm)
    real_history = h.port.history

    async def stale(*, peer=None, need_id=None):
        rows = await real_history(peer=peer, need_id=need_id)
        return [r for r in rows if tf.LEDGER not in (r.sender, r.recipient)]

    h.port.history = stale
    await h.turn(cit, confirm)
    check("cronologia in ritardo: nessun secondo hold e nessun secondo commit",
          len(h.out(tf.LEDGER, "hold")) == 1 and len(h.out(tf.LEDGER, "commit")) == 1, h)

    # Stessa request_id, mondo cambiato nel frattempo: le offerte restano le stesse.
    h = harness(REBOOK_ROWS)
    await h.turn(CUP, search("rq-I1", ""))
    h.world.slots[f"{PROC}:1"] = tf.slots_reply(ME, [R5])
    await h.turn(CUP, search("rq-I1", ""))
    out = replies(h)
    check("stessa request_id due volte: due risposte identiche (stesse offerte)",
          len(out) == 2 and out[0] == out[1] and bool(lines_of(out[0], "offer")), h)
    check("la prima risposta non e' cambiata dal mondo nuovo (niente R-5)",
          bool(out) and "slot_id=R-5" not in out[0], h)


# --- Livello 8: regole che cambiano a meta' partita (solo consultorio) ---------------------------------
# Assunzioni (MACH-1.2, "RULE SYNC"; il formato di `rules` non e' nel kit, vedi _rule_on):
# - Il Ledger rifiuta hold/commit con un codice. Verso il CUP: PRESCRIPTION_EXPIRED, CONSENT_MISSING,
#   NO_CAPACITY diventano `cancel offer_id=... slot_id=... reason=<codice in minuscolo>`; ogni altro
#   codice diventa `hold_refused offer_id=... slot_id=... ledger_code=<codice>`.
# - `rules` si rilegge a ogni turno in cui serve (qui: confirm di un CUP di un'altra ASST senza
#   cross_asst_consent_ref). P2 acceso: niente hold, cancel reason=consent_missing. P2 spento: hold.
OTHER_CUP = "agent:t09/booking_centre"  # un'altra ASST (team diverso da quello del consultorio)
CONFIRM = ("confirm offer_id=of-{s} slot_id={s} citizen=citizen:t09/c-1 consent_ref=cons-{s} "
           "request_id={r}")


def live_rules(h: tf.Harness) -> None:
    """Il Ledger risponde a `rules` mentre l'agente aspetta, come fa il Relay (non al turno dopo)."""
    post = h.port.post

    async def wrapped(*, to, message_type, body, need_id, conversation_id, traceparent):
        mid = await post(to=to, message_type=message_type, body=body, need_id=need_id,
                         conversation_id=conversation_id, traceparent=traceparent)
        if to == tf.LEDGER and str(body.get("text", "")).strip() == "rules":
            h.port.log.append(tf.Message(type="chat", sender=tf.LEDGER, recipient=ME,
                                         msg_id=tf.uuid4().hex, need_id=need_id,
                                         conversation_id=conversation_id,
                                         body={"text": h.world.rules}))
        return mid

    h.port.post = wrapped


async def codici_del_ledger() -> None:
    print("Rifiuti del Ledger verso il CUP")
    cases = [("hold", "NO_CAPACITY", "cancel", "reason=no_capacity"),
             ("hold", "PRESCRIPTION_EXPIRED", "cancel", "reason=prescription_expired"),
             ("hold", "CONSENT_MISSING", "cancel", "reason=consent_missing"),
             ("commit", "NO_CAPACITY", "cancel", "reason=no_capacity"),
             ("hold", "SLOT_UNKNOWN", "hold_refused", "ledger_code=SLOT_UNKNOWN"),
             ("commit", "RULE_VIOLATION", "hold_refused", "ledger_code=RULE_VIOLATION")]
    for op, code, head, token in cases:
        h = tf.Harness(CAP, ME, tf.World(ME, {f"{PROC}:1": tf.slots_reply(ME, REBOOK_ROWS)},
                                         refuse={op: code}))
        await h.turn(CUP, search("rq-L1", ""))
        await h.turn(CUP, CONFIRM.format(s="R-1", r="rq-L1").replace("t09", "t01"))
        out = h.out(CUP, head)
        other = h.out(CUP, "hold_refused" if head == "cancel" else "cancel")
        check(f"{op} rifiutato con {code}: {head} {token} con offer_id e slot_id",
              len(out) == 1 and token in out[0].split() and "offer_id=of-R-1" in out[0]
              and "slot_id=R-1" in out[0] and not other, h)
        check(f"{op} {code}: nessuna ricevuta al CUP", not h.out(CUP, "booking.receipt"), h)


async def regole_a_meta_partita() -> None:
    print("P2 con rules riletto a ogni turno")
    h = harness(REBOOK_ROWS)
    live_rules(h)
    await h.turn(OTHER_CUP, search("rq-P1", ""))
    h.world.rules = "rules P2=on"
    await h.turn(OTHER_CUP, CONFIRM.format(s="R-2", r="rq-P1"))
    check("P2 acceso, nessun cross_asst_consent_ref: nessun hold e cancel consent_missing",
          not h.out(tf.LEDGER, "hold")
          and any("reason=consent_missing" in t for t in h.out(OTHER_CUP, "cancel")), h)
    await h.turn(OTHER_CUP, CONFIRM.format(s="R-3", r="rq-P1") + " cross_asst_consent_ref=cons-x")
    holds = h.out(tf.LEDGER, "hold")
    check("P2 acceso con il consenso cross_asst: hold con quel consent_ref",
          len(holds) == 1 and "slot_id=R-3" in holds[0] and "consent_ref=cons-x" in holds[0], h)
    h.world.rules = "rules none"
    await h.turn(OTHER_CUP, CONFIRM.format(s="R-5", r="rq-P1"))
    holds = h.out(tf.LEDGER, "hold")
    check("P2 tornato spento: la regola e' riletta, hold su R-5 con il consent_ref della conferma",
          len(holds) == 2 and "slot_id=R-5" in holds[-1] and "consent_ref=cons-R-5" in holds[-1], h)

    print("P3: la riserva urgente solo a priorita' U")
    reserve = rslot("R-U", DOC, "2026-11-23T14:00:00.000Z", "mon").replace(
        "urgent_reserve=false", "urgent_reserve=true")
    for priority, expected in (("U", True), ("D", False)):
        h = harness([reserve])
        await h.turn(CUP, search(f"rq-U{priority}", "").replace("priority=D", f"priority={priority}"))
        text = " ".join(replies(h))
        check(f"priorita' {priority}: R-U (riserva urgente) {'offerto' if expected else 'mai offerto'}",
              ("slot_id=R-U" in text) == expected, h)


# --- Hold scaduto o fence vecchio: una sola nuova prenotazione prima di annullare --------------------
# Console 21/11 (percorsi 256, 229, 216, 248): dopo il confirm il Ledger rifiutava il commit con
# EXPIRED o STALE_FENCE e il consultorio annullava subito al cittadino, che restava senza
# prenotazione. Una sola riprova (nuovo hold + nuovo commit) per slot; poi il cancel.


class Expiring(tf.World):
    """I primi `times` commit trovano l'hold scaduto o con fence vecchio (codice `code`)."""

    def __init__(self, me, slots, code="EXPIRED", times=1):
        super().__init__(me, slots)
        self.code, self.left = code, times

    def answer(self, text):
        if text.split()[0] == "commit" and self.left > 0:
            self.left -= 1
            hold = dict(w.split("=", 1) for w in text.split()[1:] if "=" in w)["hold_id"]
            return f"refused commit hold_id={hold} code={self.code}"
        return super().answer(text)


async def riprova_hold_scaduto() -> None:
    print("Hold scaduto o fence vecchio: una sola riprova")
    cit = "citizen:t02/c-0400"
    confirm = "confirm offer_id=of-R-1 consent_ref=cons-N-booking"
    for code in ("EXPIRED", "STALE_FENCE"):
        h = tf.Harness(CAP, ME, Expiring(ME, {f"{PROC}:1": tf.slots_reply(ME, REBOOK_ROWS)}, code))
        await h.turn(cit, "vorrei una visita ginecologica")
        await h.turn(cit, confirm)
        receipts = h.out(cit, "booking.receipt")
        check(f"cittadino, commit rifiutato {code} una volta: due hold e due commit su R-1",
              len(h.out(tf.LEDGER, "hold")) == 2 and len(h.out(tf.LEDGER, "commit")) == 2
              and all("slot_id=R-1" in t for t in h.out(tf.LEDGER, "hold")), h)
        check(f"cittadino, {code}: una ricevuta su R-1 e nessun cancel", len(receipts) == 1
              and "slot_id=R-1" in receipts[0] and not h.out(cit, "cancel"), h)
    h = tf.Harness(CAP, ME, Expiring(ME, {f"{PROC}:1": tf.slots_reply(ME, REBOOK_ROWS)}, "STALE_FENCE"))
    await h.turn(CUP, search("rq-X1", ""))
    await h.turn(CUP, "confirm offer_id=of-R-1 slot_id=R-1 citizen=citizen:t01/c-9 "
                      "consent_ref=cons-1 request_id=rq-X1")
    receipts = h.out(CUP, "booking.receipt")
    check("CUP, STALE_FENCE una volta: due hold e una ricevuta al CUP, nessun cancel",
          len(h.out(tf.LEDGER, "hold")) == 2 and len(receipts) == 1 and not h.out(CUP, "cancel"), h)
    h = tf.Harness(CAP, ME, Expiring(ME, {f"{PROC}:1": tf.slots_reply(ME, REBOOK_ROWS)}, "EXPIRED", 99))
    await h.turn(cit, "vorrei una visita ginecologica")
    await h.turn(cit, confirm)
    cancels = h.out(cit, "cancel")
    check("sempre EXPIRED: una sola riprova (due hold, non di piu') e un solo cancel al cittadino",
          len(h.out(tf.LEDGER, "hold")) == 2 and len(cancels) == 1 and "reason=EXPIRED" in cancels[0], h)
    h = tf.Harness(CAP, ME, Expiring(ME, {f"{PROC}:1": tf.slots_reply(ME, REBOOK_ROWS)}, "NO_CAPACITY", 99))
    await h.turn(cit, "vorrei una visita ginecologica")
    await h.turn(cit, confirm)
    check("NO_CAPACITY non si riprova: un solo hold e il cancel",
          len(h.out(tf.LEDGER, "hold")) == 1 and bool(h.out(cit, "cancel")), h)


# --- Anticipo degli slot in ore d'agenda (un minuto reale = un'ora d'agenda) ---------------------------
# Console 21/11 (8909110001400007): offerte per venerdi' 27 alle 10:30, `confirm` 20 minuti reali dopo =
# 20 ore d'agenda: lo slot era passato, `cancel reason=EXPIRED` un secondo dopo, poi `reason=past`.
# Il cittadino risponde dopo 3-27 ore d'agenda: si offrono per primi gli slot ad almeno 30 ore
# d'agenda (il weekend non conta), poi quelli ad almeno 4 ore; sotto le 4 ore mai.


class AgendaAt(tf.World):
    def __init__(self, me, slots, now):
        super().__init__(me, slots)
        self.now = now

    def answer(self, text):
        if text.split()[0] == "agenda":
            return f"agenda agenda_now={self.now}"
        return super().answer(text)


async def anticipo_degli_slot() -> None:
    print("Anticipo degli slot in ore d'agenda")
    cit = "citizen:t02/c-0700"

    async def offered(now, rows):
        h = tf.Harness(CAP, ME, AgendaAt(ME, {f"{PROC}:1": tf.slots_reply(ME, rows)}, now))
        await h.turn(cit, "vorrei una visita ginecologica")
        return [tokens(t).get("slot_id") for t in h.out(cit, "offer")], h

    mon = "2026-11-23T08:00:00+01:00"  # lunedi' 08:00 d'agenda
    rows = [slot("N-3h", "2026-11-23T10:00:00.000Z", "mon"),   # 11:00 locali: 3 ore, mai
            slot("A-6h", "2026-11-23T13:00:00.000Z", "mon"),   # 14:00: 6 ore
            slot("B-26h", "2026-11-24T09:30:00.000Z", "tue"),  # martedi' 10:30: 26 ore e mezza
            slot("C-50h", "2026-11-25T09:30:00.000Z", "wed"),  # mercoledi' 10:30: 50 ore e mezza
            slot("D-52h", "2026-11-25T11:00:00.000Z", "wed")]
    got, h = await offered(mon, rows)
    check("lunedi' 08:00: prima gli slot a 30 ore o piu' (C, D), poi A; B dopo; N-3h mai",
          got == ["C-50h", "D-52h", "A-6h"], h)

    fri = "2026-11-20T17:00:00+01:00"  # venerdi' 17:00: il weekend non esiste nell'agenda
    rows = [slot("MON-17h", "2026-11-23T09:30:00.000Z", "mon"),  # lunedi' 10:30: 17 ore e mezza d'agenda
            slot("TUE-41h", "2026-11-24T09:30:00.000Z", "tue"),  # 41 ore e mezza
            slot("WED-65h", "2026-11-25T09:30:00.000Z", "wed")]
    got, h = await offered(fri, rows)
    check("venerdi' 17:00: lunedi' e' a 17 ore d'agenda, non 65: prima martedi' e mercoledi'",
          got == ["TUE-41h", "WED-65h", "MON-17h"], h)


# --- MACH-1.3 e slot passati ---------------------------------------------------------------------
# - Una ricerca con deadline=/earliest= (data e ora) non riceve slot fuori finestra, nemmeno rilassati.
# - Al confirm, uno slot passato o a meno di un'ora non va in hold: cancel reason=past e nuove offerte.
# - L'orologio d'agenda si estrapola dal tempo reale: prima il consultorio riproponeva slot passati.


async def mach13_e_slot_passati() -> None:
    print("MACH-1.3 e slot passati")
    h = harness([V1, X_DAYS])
    await h.turn(CUP, search("rq-D1", "mach=1.3 deadline=2026-11-24T12:00:00Z"))
    out = " ".join(replies(h))
    check("deadline= con data: V-1 (24/11 10:00Z) offerto, X-days (25/11) mai, nemmeno rilassato",
          "slot_id=V-1" in out and "X-days" not in out, h)
    h = harness([V1])
    await h.turn(CUP, search("rq-D2", "mach=1.3 earliest=2026-11-24T12:00:00Z"))
    out = " ".join(replies(h))
    check("earliest= con data dopo lo slot: nessuna offerta, cancel no_availability",
          "slot_id=V-1" not in out and "reason=no_availability" in out, h)

    cit = "citizen:t02/c-0900"
    near = slot("P-near", "2026-11-23T13:00:00.000Z", "mon")   # 14:00 locali, 6 ore dopo le 08:00
    later = slot("P-later", "2026-11-25T09:30:00.000Z", "wed")
    h = harness([near, later])
    await h.turn(cit, "vorrei una visita ginecologica")
    h.port.log.append(tf.Message(type="chat", sender=tf.LEDGER, recipient=ME, msg_id="ag-late",
                                 need_id=h.need, body={"text": "agenda agenda_now=2026-11-23T13:30:00+01:00"}))
    await h.turn(cit, "confirm offer_id=of-P-near consent_ref=cons-N-booking")
    check("confirm di uno slot a mezz'ora: nessun hold", not any("slot_id=P-near" in t for t in h.out(tf.LEDGER, "hold")), h)
    check("... e cancel reason=past al cittadino", any("reason=past" in t and "slot_id=P-near" in t
                                                       for t in h.out(cit, "cancel")), h)

    from datetime import datetime, timezone
    rows = [tf.Message(type="chat", sender=tf.LEDGER, recipient=ME, msg_id="a", need_id="N",
                       body={"text": "agenda agenda_now=2026-11-23T08:00:00Z"}, sent_at="2026-11-21T04:00:00Z")]
    got = tf_mod_agenda(rows, datetime(2026, 11, 21, 4, 20, tzinfo=timezone.utc))
    check("orologio: 20 minuti reali dopo la lettura = 20 ore d'agenda dopo", got == datetime(2026, 11, 24, 4, 0, tzinfo=timezone.utc))


def tf_mod_agenda(rows, real_now):
    return tf.load(CAP, ME)._agenda_now(rows, real_now)


async def run() -> None:
    await righe_vere()
    await criteri_estesi()
    await offerte_rilassate()
    await sedia_a_rotelle()
    if ROLE == "family_counseling":
        await riprenota_cittadino()
        await riprenota_cup()
        await idempotenza()
        await riprova_hold_scaduto()
        await mach13_e_slot_passati()
        await anticipo_degli_slot()
        await codici_del_ledger()
        await regole_a_meta_partita()
    print(f"\n{'TUTTO OK' if not tf.FAILS else str(len(tf.FAILS)) + ' FALLITE'}")
    sys.exit(1 if tf.FAILS else 0)


if __name__ == "__main__":
    asyncio.run(run())
