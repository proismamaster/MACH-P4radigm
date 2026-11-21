"""Prove locali per i fix di GP e specialist, con l'SDK vero e il City finto di tools/test_facility.py.

Uso, dalla cartella della repo: python tools/test_fix.py
"""

import asyncio
import importlib.util
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("tf", os.path.join(REPO, "tools", "test_facility.py"))
tf = importlib.util.module_from_spec(spec)
sys.argv = [sys.argv[0]]
spec.loader.exec_module(tf)

FAILS = []


def check(name, cond, h=None):
    print(("  PASS " if cond else "  FAIL ") + name)
    if not cond:
        FAILS.append(name)
        if h:
            h.dump()


class World(tf.World):
    def answer(self, text):
        words = text.split()
        f = dict(w.split("=", 1) for w in words[1:] if "=" in w)
        if words[0] == "report":
            return f"reported booking_id={f['booking_id']}"
        if words[0] == "prescribe":
            return (f"prescribed prescription_number={f['prescription_number']} patient={f['patient']} "
                    f"procedure={f['procedure']} priority={f['priority']} state=issued")
        return super().answer(text)


def harness(cap, me, role_card="facility"):
    folder = {"gp": "gp", "specialist_care.cardiology": "specialist"}[cap]
    tf.AGENT_FILE = os.path.join(REPO, "asst", folder, "agent", "agent.py")
    h = tf.Harness.__new__(tf.Harness)
    card = tf.CARD.replace("role: facility", f"role: {role_card}")
    old = tf.CARD
    tf.CARD = card
    try:
        h.mod = tf.load(cap, me)
    finally:
        tf.CARD = old
    h.me, h.port, h.world, h.need = me, tf.Port(me), World(me), "N-2026-11-23-0001"
    return h


SPEC = "agent:t02/specialist"
CIT = "citizen:t01/c-0042"


async def specialist(answer, want_ref):
    # Since 21/11 09:40 the report is archived at the end of the check-in turn when no answer comes
    # within the short wait (report_missing -1, journey 1820005). Here the answer arrives in a LATER
    # turn, so the report is the unshared one and the late answer adds nothing. The answer inside
    # the wait (shared report) is covered by tools/test_specialist_referto.py.
    h = harness("specialist_care.cardiology", SPEC)
    h.mod._CONSENT_WAIT = 0.2
    await h.turn(CIT, "checkin booking_id=BK-1")
    asks = h.out(CIT, "consent")
    check("chiede consenso report_sharing dopo il check-in", len(asks) == 1 and "purpose=report_sharing" in asks[0], h)
    reports = h.out("city:ledger", "report")
    check("senza risposta nel turno del check-in: referto archiviato senza condivisione",
          len(reports) == 1 and "consent_ref" not in reports[0], h)
    check("referto comunicato al cittadino", len(h.out(CIT, "report")) == 1, h)
    await h.turn(CIT, answer)
    await h.turn(CIT, answer)
    check("risposta tardiva (anche ripetuta): nessun secondo referto", len(h.out("city:ledger", "report")) == 1, h)


GP = "agent:t02/gp"


async def gp(text, want):
    h = harness("gp", GP, role_card="gp")
    await h.turn(CIT, text)
    rx = h.out(CIT, "prescription")
    esc = h.out(CIT, "escalate.emergency")
    if want == "escalate":
        check(f"escalation: {text[:40]}", len(esc) == 1 and not rx, h)
    else:
        check(f"ricetta {want}: {text[:40]}", len(rx) == 1 and f"procedure={want}" in rx[0], h)


async def main():
    print("Specialist - consenso dato")
    await specialist("Va bene. consent consent_ref=cons-77 purpose=report_sharing", "cons-77")
    print("Specialist - consenso rifiutato")
    await specialist("No grazie, preferisco di no.", None)
    print("Specialist - consenso per altro scopo ignorato")
    h = harness("specialist_care.cardiology", SPEC)
    h.mod._CONSENT_WAIT = 0.2
    await h.turn(CIT, "checkin booking_id=BK-1")
    await h.turn(CIT, "ok consent consent_ref=cons-9-booking purpose=booking")
    reports = h.out("city:ledger", "report")
    check("consent_ref di prenotazione mai usato per il referto",
          len(reports) == 1 and "cons-9-booking" not in reports[0], h)
    check("il consenso per un altro scopo non è una risposta", not h.mod._consent_reply(h.port.log[-1])[0], h)
    print("GP - testo libero vero dalla console")
    await gp("Ciao! Ho mal di schiena da un po' di settimane, vorrei fare vedere.", "VIS-FIS")
    await gp("ciao doc, raga tipo il cuore che batte a mille ultimamente, lowkey vorrei un check", "VIS-CARD")
    await gp("Buongiorno dottore, ho un forte dolore al petto da stamattina", "escalate")
    print("GP - red flag nascosta letta dalla tabella del world (livello 8)")
    h = harness("gp", GP, role_card="gp")
    # GP 1.0.9: without a world after the short wait the built-in table prescribes (84 world of 84 had no
    # protocols). Empty here, so the world's own red flags are what decides.
    h.mod._PROTOCOLS = {}
    base = World.answer

    def world_with_flags(text, _w=h.world):
        if text.startswith("world"):
            return ("world page=1/1\nsymptom_code=SYM-BACK procedure=VIS-FIS priority=B "
                    "red_flags=incontinenza|febbre_alta")
        return base(_w, text)
    h.world.answer = world_with_flags
    await h.turn(CIT, "Ho mal di schiena da settimane e da ieri anche febbre alta")
    check("escalation con red flag del world", len(h.out(CIT, "escalate.emergency")) == 1, h)
    check("nessuna ricetta dopo la red flag", not h.out(CIT, "prescription") and not h.out("city:ledger", "prescribe"), h)
    h = harness("gp", GP, role_card="gp")
    h.world.answer = world_with_flags
    await h.turn(CIT, "Ho mal di schiena da settimane")
    check("senza red flag la ricetta parte normalmente", len(h.out(CIT, "prescription")) == 1, h)
    print("GP - DUPLICATE: ricetta annunciata solo dopo averla riletta")
    h = harness("gp", GP, role_card="gp")
    def dup_world(text, _w=h.world):
        if text.startswith("prescribe"):
            n = text.split("prescription_number=")[1].split()[0]
            return f"refused prescribe prescription_number={n} code=DUPLICATE"
        if text.startswith("prescription "):
            n = text.split("prescription_number=")[1].split()[0]
            return f"prescription prescription_number={n} patient=citizen:altro procedure=VIS-FIS priority=B state=issued"
        return World.answer(_w, text)
    h.world.answer = dup_world
    await h.turn(CIT, "Ho mal di schiena da settimane")
    # GP 1.0.10 announces before the Ledger reply: our number is sha256 of need and citizen, so another
    # patient's DUPLICATE cannot come from it. What stays true: never a second announcement.
    check("DUPLICATE: al massimo un annuncio", len(h.out(CIT, "prescription")) <= 1, h)
    print("Specialist - due risposte al consenso: un solo referto, check-in con ledger_ref")
    h = harness("specialist_care.cardiology", SPEC)
    h.world.answer = lambda text, _w=h.world: (
        "checked_in booking_id=BK-1 citizen=" + CIT + " ledger_ref=LR-9" if text.startswith("checkin")
        else World.answer(_w, text))
    await h.turn(CIT, "checkin booking_id=BK-1")
    check("check-in al cittadino con ledger_ref", any("ledger_ref=LR-9" in t for t in h.out(CIT, "checkin")), h)
    await asyncio.gather(
        h.turn(CIT, "Va bene. consent consent_ref=cons-1 purpose=report_sharing"),
        h.turn(CIT, "Sì confermo. consent consent_ref=cons-1 purpose=report_sharing"),
    )
    check("un solo referto al Ledger con risposte concorrenti", len(h.out("city:ledger", "report")) == 1, h)
    print("GP - Ledger muto: nessuna ricetta annunciata senza conferma")
    h = harness("gp", GP, role_card="gp")
    h.world.answer = lambda text: None if text.startswith("prescribe") else World.answer(h.world, text)
    h.mod._PULL_PAUSE = 0
    await h.turn(CIT, "Ho mal di schiena da settimane")
    check("prescribe inviato al Ledger", len(h.out("city:ledger", "prescribe")) == 1, h)
    # GP 1.0.10: the number is ours and the Ledger keeps it, so it is announced without waiting (14:02 wave).
    check("ricetta annunciata subito dopo prescribe, con il nostro numero", len(h.out(CIT, "prescription")) == 1, h)
    number = h.out("city:ledger", "prescribe")[0].split("prescription_number=")[1].split()[0] if h.out("city:ledger", "prescribe") else "x"
    await h.turn("city:ledger", f"prescribed prescription_number={number} patient={CIT} procedure=VIS-FIS priority=B state=issued")
    check("ricetta annunciata quando arriva prescribed", len(h.out(CIT, "prescription")) == 1, h)
    print("GP - risposta Ledger in altra conversazione")
    h = harness("gp", GP, role_card="gp")
    await h.turn(CIT, "Ho mal di schiena da settimane")
    check("ricetta annunciata (stessa conversazione)", len(h.out(CIT, "prescription")) == 1, h)
    print("FALLITE:", FAILS if FAILS else "nessuna")
    sys.exit(1 if FAILS else 0)


asyncio.run(main())
