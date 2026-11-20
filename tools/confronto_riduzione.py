import asyncio, os, sys, re
R, ROLE, FULL, SMALL = sys.argv[1:5]
src = open(os.path.join(R, "tools", "test_fix.py"), encoding="utf-8").read().split("asyncio.run(main())")[0]
ns = {"__file__": os.path.join(R, "tools", "test_fix.py"), "__name__": "x"}
sys.argv = [sys.argv[0]]
exec(compile(src, "tf", "exec"), ns)
tf, World = ns["tf"], ns["World"]
import importlib.util, tempfile
from uuid import uuid4
def _load(cap, aid):
    card = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
    card.write(tf.CARD.format(aid=aid, cap=cap)); card.close()
    os.environ["CITY_CARD"] = card.name; os.environ.pop("CITY_ROLE", None)
    name = f"agent_{uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, tf.AGENT_FILE)
    mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod
    spec.loader.exec_module(mod); mod._PULL_TRIES = 1
    return mod
tf.load = _load
CIT, ME, HOSP = "citizen:t01/c-1", "agent:t02/" + ROLE, "agent:t02/hospital"
RX = "prescription_number-AB12"
ROWS = [f"slot_id=S-{i} doctor_id={d} facility={HOSP} procedure=VIS-FIS at=2026-11-2{4+i//3}T0{8+i%3}:00:00+01:00 day={dd} free=1"
        for i, (d, dd) in enumerate([("h1", "tue"), ("D-3", "tue"), ("h3", "tue"), ("h2", "wed"), ("h1", "wed")])]
class W(World):
    def answer(self, text):
        if text.startswith("prescription "):
            return f"prescription prescription_number={RX} patient={CIT} procedure=VIS-FIS priority=B state=issued"
        if text.startswith("world"):
            return self.slots.get("all", "slots page=1/1")
        return World.answer(self, text)
async def run(path, steps, world_rows=True):
    tf.AGENT_FILE = path
    h = tf.Harness.__new__(tf.Harness)
    card = tf.CARD
    tf.CARD = card.replace("role: facility", f"role: {ROLE}")
    try: h.mod = tf.load(ROLE, ME)
    finally: tf.CARD = card
    h.mod._PULL_PAUSE = 0
    h.me, h.port, h.need = ME, tf.Port(ME), "N-1"
    h.world = W(ME, {"all": tf.slots_reply(ME, ROWS)} if world_rows else {})
    for sender, text in steps:
        if "OFFER" in text:
            offer = next((w.split("=",1)[1] for r in h.port.log if r.sender == ME for w in r.text.split() if w.startswith("offer_id=")), "none")
            text = text.replace("OFFER", offer)
        await h.turn(sender, text)
    return [re.sub(r"[0-9a-f]{12}|[0-9a-f]{8,}", "ID", f"{r.sender}>{r.recipient} {r.text}") for r in h.port.log]
CUP = {
 "richiesta con ricetta": [(CIT, f"need.request prescription_number={RX} lang=it")],
 "richiesta in inglese": [(CIT, f"need.request prescription_number={RX} lang=en")],
 "richiesta senza ricetta": [(CIT, "Buongiorno, vorrei prenotare una visita")],
 "nessun orario locale (cross-ASST, Index vuoto)": [(CIT, f"need.request prescription_number={RX} lang=it")],
 "ricevuta dalla struttura": [(CIT, f"need.request prescription_number={RX} lang=it"), (HOSP, "booking.receipt booking_id=BK-1 ledger_ref=LR-1")],
 "domanda indirizzo": [(HOSP, "data.request purpose=booking fields=address")],
 "scelta e conferma": [(CIT, f"need.request prescription_number={RX} lang=it"), (CIT, "confirm offer_id=OFFER consent_ref=cons-1")],
 "scelta e annullamento struttura": [(CIT, f"need.request prescription_number={RX} lang=it"), (CIT, "confirm offer_id=OFFER consent_ref=cons-1"), (HOSP, "cancel offer_id=OFFER reason=slot_taken")],
}
GP = {
 "mal di schiena": [(CIT, "Ho mal di schiena da settimane")],
 "cuore": [(CIT, "sento il cuore che batte a mille")],
 "dolore al petto": [(CIT, "ho un forte dolore al petto")],
 "sintomo ignoto poi consenso": [(CIT, "non sto bene"), (CIT, "ok consent consent_ref=c-1 purpose=descrizione_disturbo")],
 "rinnovo": [(CIT, f"need.request prescription_number={RX}")],
 "richiesta clinica": [(CIT, "che dose di ibuprofene devo prendere?")],
}
async def go():
    bad = 0
    for name, steps in (CUP if ROLE == "booking_centre" else GP).items():
        rows = "Index vuoto" not in name
        out = []
        for p in (FULL, SMALL):
            try: out.append(await run(p, steps, rows))
            except Exception as e: out.append(["EXC " + type(e).__name__ + " " + str(e)[:80]]); print("  ECCEZIONE", p[-40:], type(e).__name__, str(e)[:120])
        same = out[0] == out[1]; bad += not same
        print(("UGUALE " if same else "DIVERSO ") + name, len(out[0]), "messaggi")
        if not same: print("  completo:", out[0]); print("  ridotto: ", out[1])
    sys.exit(bad)
asyncio.run(go())
