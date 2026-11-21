"""Simulazione: i percorsi veri del 21/11 rigiocati sul CUP (versione attuale e versioni precedenti).

Uso, dalla cartella della repo:
    python tools/sim_percorsi.py <cartella con journey-*.json> [agent.py ...]
Senza agent.py usa asst/booking_centre/agent/agent.py.

Modello (dai dati della notte, vedi team/REVISIONE.md):
- Agenda: 02/12 15:00Z alle 04:17:46Z reali, 60 ore d'agenda per ora reale, sabato e domenica saltati
  (verificato: 01400007 offre venerdi' 27/11 alle 02:55 reali, 197/221/280 sui rifiuti `past`).
- Mondo della nostra ASST: h1 (lun-mer, f), h2 (mer-ven, m), h3 (mar-gio, m), s1 (lun/mer/ven, m),
  s2 (mar/gio, f) alle 10:30, 12:00, 14:30, 16:00 UTC, come gli slot_id veri.
- Il cittadino: scadenza dalla sua nascita (primo messaggio al medico) + 2 (B) o 5 (D) giorni d'agenda;
  giorni nominati nel testo; genere dedotto dai suoi rifiuti `gender` (il contrario del medico rifiutato);
  decide DECIDE minuti reali dopo l'offerta e accetta il primo slot ancora valido.
- Il CUP risponde LAT minuti reali dopo il messaggio; al confirm passa altri LAT minuti.
Esito per percorso: prenotato al primo giro, al secondo giro (dopo i rifiuti), oppure no.
"""

from __future__ import annotations

import glob
import importlib.util
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

from city_sdk.city import LEDGER, Message

UTC = timezone.utc
ANCHOR_REAL = datetime(2026, 11, 21, 4, 17, 46, tzinfo=UTC)
ANCHOR_AGENDA = datetime(2026, 12, 2, 15, 0, tzinfo=UTC)
DOCS = {"h1": ("f", {"mon", "tue", "wed"}, "VIS-FIS"), "h2": ("m", {"wed", "thu", "fri"}, "VIS-FIS"),
        "h3": ("m", {"tue", "thu"}, "VIS-FIS"), "s1": ("m", {"mon", "wed", "fri"}, "VIS-CARD"),
        "s2": ("f", {"tue", "thu"}, "VIS-CARD")}
WEEK = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
IT = {"luned": "mon", "marted": "tue", "mercoled": "wed", "gioved": "thu", "venerd": "fri",
      "lun": "mon", "mer": "wed", "gio": "thu", "ven": "fri"}


def agenda_at(real: datetime) -> datetime:
    """Agenda time at a real instant, skipping weekends in both directions."""
    delta = (real - ANCHOR_REAL) * 60
    out = ANCHOR_AGENDA
    step = timedelta(hours=1) if delta >= timedelta(0) else -timedelta(hours=1)
    left = abs(delta)
    while left > timedelta(0):
        move = min(left, timedelta(hours=1))
        out = out + (move if step > timedelta(0) else -move)
        left -= move
        while out.weekday() >= 5:
            out = out + (timedelta(days=1) if step > timedelta(0) else -timedelta(days=1))
    return out


def plus_days(start: datetime, days: int) -> datetime:
    out = start
    while days:
        out += timedelta(days=1)
        days -= out.weekday() < 5
    return out


def world(procedure: str) -> list[str]:
    lines, day = [], datetime(2026, 11, 23, tzinfo=UTC)
    while day < datetime(2026, 12, 19, tzinfo=UTC):
        name = WEEK[day.weekday()]
        for doc, (_, days, proc) in DOCS.items():
            if proc != procedure or name not in days:
                continue
            for hh, mm in ((10, 30), (12, 0), (14, 30), (16, 0)):
                at = day.replace(hour=hh, minute=mm)
                lines.append(f"slot_id=W01QQQ-asst-bicocca-{doc}-{at:%Y%m%d-%H%M} capacity=1 facility=agent:bb01ggxymm05 "
                             f"doctor_id=asst-bicocca-{doc} procedure={procedure} agenda_day={name} "
                             f"agenda_date={at:%Y-%m-%dT%H:%M:%S}.000Z urgent_reserve=false")
        day += timedelta(days=1)
    return lines


def when(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def load(path: str):
    spec = importlib.util.spec_from_file_location(f"cup_{abs(hash(path))}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def citizen_model(journey: dict) -> dict | None:
    msgs = journey["messages"]
    gp = next((m for m in msgs if m["from"] == "agent:rng5wcrzvhsj" and "prescription_number=" in m["body"].get("text", "")), None)
    to_cup = next((m for m in msgs if m["to"] == "agent:ez8cb7j167p2" and "need.request" in m["body"].get("text", "")), None)
    if gp is None or to_cup is None:
        return None
    fields = dict(t.split("=", 1) for t in gp["body"]["text"].split() if "=" in t)
    if fields.get("priority") not in ("B", "D") or fields.get("procedure") not in ("VIS-FIS", "VIS-CARD"):
        return None
    birth = min(when(m["sent_at"]) for m in msgs if m["from"].startswith("citizen"))
    words = " ".join(m["body"].get("text", "").split("need.request")[0] for m in msgs if m["from"].startswith("citizen")).lower()
    tokens = re.findall(r"[a-z]+", words.replace("ì", "i"))
    named = {IT[k] for k in IT for t in tokens if (t == k if len(k) == 3 else t.startswith(k))}
    offers = {}
    for m in msgs:
        if m["from"] == "agent:ez8cb7j167p2":
            for line in m["body"].get("text", "").splitlines():
                f = dict(t.split("=", 1) for t in line.split() if "=" in t)
                if line.startswith("offer") and "offer_id" in f:
                    offers[f["offer_id"]] = f
    refused_gender = set()
    for m in msgs:
        r = re.search(r"cancel offer_id=(\S+) reason=gender", m["body"].get("text", ""))
        if r and r.group(1) in offers:
            doc = offers[r.group(1)].get("doctor_id", "").rsplit("-", 1)[-1]
            if doc in DOCS:
                refused_gender.add(DOCS[doc][0])
    gender = {"m": "f", "f": "m"}[refused_gender.pop()] if len(refused_gender) == 1 else None
    return {"priority": fields["priority"], "procedure": fields["procedure"], "birth": birth,
            "deadline": plus_days(agenda_at(birth), {"B": 2, "D": 5}[fields["priority"]]),
            "t_cup": when(to_cup["sent_at"]), "named": named, "gender": gender,
            "text": to_cup["body"]["text"], "lang": "en" if "lang=en" in to_cup["body"]["text"] else "it"}


def accepts(c: dict, slot: dict, decide_at: datetime) -> str:
    at = when(slot["agenda_date"])
    doc = slot["doctor_id"].rsplit("-", 1)[-1]
    if at <= agenda_at(decide_at):
        return "past"
    if at > c["deadline"]:
        return "deadline"
    if c["named"] and slot["agenda_day"] not in c["named"]:
        return "day"
    if c["gender"] and DOCS[doc][0] != c["gender"]:
        return "gender"
    return ""


def offers_from(cup, c: dict, chat: list, now: datetime, cit: str) -> list[dict]:
    kwargs = dict(now=now, priority=c["priority"], lang=c["lang"], gender=cup._gender(chat, cit),
                  procedure=c["procedure"], days=cup._cup_days(chat, cit))
    if hasattr(cup, "_true_deadline"):
        try:
            kwargs["until"] = cup._true_deadline(chat, cit, c["priority"])
        except TypeError:
            pass
    try:
        slots = cup.fitting(world(c["procedure"]), **kwargs)
    except TypeError:
        kwargs.pop("until", None)
        slots = cup.fitting(world(c["procedure"]), **kwargs)
    seen, first = set(), []
    for s in slots:
        if s.get("day") not in seen:
            seen.add(s.get("day"))
            first.append(s)
    batch = (first + [s for s in slots if s not in first])[:3]
    return [{"agenda_date": s.get("at") or s.get("agenda_date"), "agenda_day": s.get("day") or s.get("agenda_day"),
             "doctor_id": s["doctor_id"], "slot_id": s["slot_id"]} for s in batch]


def simulate(cup, c: dict, lat: float, decide: float) -> str:
    cit = "citizen:sim"
    t_reply = c["t_cup"] + timedelta(minutes=lat)
    now = agenda_at(t_reply)
    chat = [Message(type="chat", sender=cit, recipient="agent:cup", msg_id="c1", need_id="N", body={"text": c["text"]},
                    sent_at=c["t_cup"].isoformat().replace("+00:00", "Z")),
            Message(type="chat", sender=LEDGER, recipient="agent:cup", msg_id="ag", need_id="N",
                    body={"text": f"agenda agenda_now={now:%Y-%m-%dT%H:%M:%S}Z"}, sent_at=t_reply.isoformat().replace("+00:00", "Z"))]
    for round_no in (1, 2):
        batch = offers_from(cup, c, chat, now, cit)
        if not batch:
            return f"nessuna offerta al giro {round_no}"
        decide_at = t_reply + timedelta(minutes=decide)
        verdicts = [accepts(c, s, decide_at) for s in batch]
        if "" in verdicts:
            s = batch[verdicts.index("")]
            confirm_at = decide_at + timedelta(minutes=lat)
            if when(s["agenda_date"]) <= agenda_at(confirm_at) + timedelta(hours=1):
                return f"slot passato al confirm (giro {round_no})"
            return f"prenotato al giro {round_no}"
        # the citizen refuses every offer: the CUP learns and offers again
        for i, (s, why) in enumerate(zip(batch, verdicts)):
            oid = f"of-{round_no}-{i}"
            chat.append(Message(type="chat", sender="agent:cup", recipient=cit, msg_id=f"o{round_no}{i}", need_id="N",
                                body={"text": f"offer offer_id={oid} slot_id={s['slot_id']} doctor_id={s['doctor_id']} "
                                              f"agenda_date={s['agenda_date']} agenda_day={s['agenda_day']}"}))
            chat.append(Message(type="chat", sender=cit, recipient="agent:cup", msg_id=f"r{round_no}{i}", need_id="N",
                                body={"text": f"no cancel offer_id={oid} reason={why}"}))
        t_reply = decide_at + timedelta(minutes=lat)
        now = agenda_at(t_reply)
        chat.append(Message(type="chat", sender=LEDGER, recipient="agent:cup", msg_id=f"ag{round_no}", need_id="N",
                            body={"text": f"agenda agenda_now={now:%Y-%m-%dT%H:%M:%S}Z"},
                            sent_at=t_reply.isoformat().replace("+00:00", "Z")))
        last = verdicts
    return "rifiutato: " + "/".join(sorted(set(last)))


def main() -> None:
    folder = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/Downloads")
    agents = sys.argv[2:] or [os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                           "asst", "booking_centre", "agent", "agent.py")]
    seen, citizens = set(), []
    for path in sorted(glob.glob(os.path.join(folder, "journey-*.json"))):
        data = json.load(open(path, encoding="utf-8"))
        nid = data["journey"]["need_id"]
        if nid in seen:
            continue
        seen.add(nid)
        c = citizen_model(data)
        if c:
            citizens.append((nid[-10:], c))
    print(f"{len(citizens)} percorsi con CUP, priorita' B/D")
    for agent in agents:
        cup = load(agent)
        for lat, decide in ((4, 4), (1, 4), (2, 8), (1, 15)):
            results = [simulate(cup, c, lat, decide) for _, c in citizens]
            booked = sum(r.startswith("prenotato") for r in results)
            print(f"\n{os.path.relpath(agent)}  latenza CUP {lat} min, decisione {decide} min: {booked}/{len(results)} prenotati")
            for (nid, c), r in zip(citizens, results):
                print(f"  {nid} {c['priority']} giorni={'/'.join(sorted(c['named'])) or '-'} genere={c['gender'] or '-'}: {r}")


if __name__ == "__main__":
    main()
