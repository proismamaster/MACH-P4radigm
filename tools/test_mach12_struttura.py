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


R1 = rslot("R-1", DOC, "2026-11-24T09:30:00.000Z", "tue")    # quello prenotato e poi annullato
R2 = rslot("R-2", DOC, "2026-11-24T13:30:00.000Z", "tue")    # stessa dottoressa
R3 = rslot("R-3", DOC, "2026-11-25T09:30:00.000Z", "wed")    # stessa dottoressa
R4 = rslot("R-4", DOC2, "2026-11-23T14:00:00.000Z", "mon")   # altra dottoressa, la piu' presto
R5 = rslot("R-5", DOC2, "2026-11-26T09:00:00.000Z", "thu")   # altra dottoressa, fuori dal limite di 3
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


async def run() -> None:
    await righe_vere()
    await criteri_estesi()
    await offerte_rilassate()
    await sedia_a_rotelle()
    if ROLE == "family_counseling":
        await riprenota_cittadino()
        await riprenota_cup()
        await idempotenza()
    print(f"\n{'TUTTO OK' if not tf.FAILS else str(len(tf.FAILS)) + ' FALLITE'}")
    sys.exit(1 if tf.FAILS else 0)


if __name__ == "__main__":
    asyncio.run(run())
