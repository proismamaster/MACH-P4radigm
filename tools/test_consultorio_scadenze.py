"""Consultorio: scadenze di priorità in giorni di AGENDA (accesso diretto e ricerche dei CUP).

Dalla cartella della repo: python tools/test_consultorio_scadenze.py
Il kit (e19-rules.md, ADR-124): sabato e domenica di agenda non esistono. B = entro 2 giorni di agenda,
D = entro 5. Il codice usava `now + timedelta(days=N)` (giorni di calendario): di giovedì la finestra
di una B finiva sabato e ogni slot di lunedì veniva scartato (stesso errore già corretto in CUP e ospedale).
"""

import importlib.util
import os
import sys
import unittest
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location(
    "fc_agent", os.path.join(REPO, "asst", "family_counseling", "agent", "agent.py"))
agent = importlib.util.module_from_spec(spec)
sys.modules["fc_agent"] = agent
spec.loader.exec_module(agent)

ME = "agent:nkh372rd16yq"


def now(day, hour=8):
    return datetime(2026, 11, day, hour, 0, tzinfo=timezone.utc)


def line(slot_id, at):
    return (f"slot_id={slot_id} doctor_id=asst-bicocca-c1 facility={ME} procedure=CONS-GIN "
            f"at=2026-11-{at}:00.000Z free=1")


def direct(priority, current, *rows):
    return [s["slot_id"] for s in agent.fitting(list(rows), now=current, priority=priority, lang="it",
                                                procedure="CONS-GIN")]


def search(priority, current, *rows):
    slots, _ = agent._facility_slots(list(rows), now=current, priority=priority, procedure="CONS-GIN", me=ME)
    return [s["slot_id"] for s in slots]


class AgendaDeadlineTests(unittest.TestCase):
    def check(self, fn):
        # Giovedì 19 + 2 giorni di agenda = lunedì 23.
        self.assertEqual(fn("B", now(19), line("fri", "20T14:30"), line("mon", "23T07:00")), ["fri", "mon"])
        # Venerdì 20 + 2 = martedì 24 alle 08:00. Martedì è oltre le 30 ore d'agenda (il weekend non
        # conta), lunedì no: martedì viene prima.
        self.assertEqual(fn("B", now(20), line("mon", "23T10:00"), line("tue", "24T07:00"),
                            line("late", "24T09:00")), ["tue", "mon"])
        # D di giovedì 19 = giovedì 26 alle 08:00: mercoledì 25 sì, giovedì 26 alle 10:00 no.
        self.assertEqual(fn("D", now(19), line("wed", "25T10:00"), line("next", "26T10:00")), ["wed"])
        # Mercoledì 25 + 2 = venerdì 27: nessun fine settimana in mezzo, come prima.
        self.assertEqual(fn("B", now(25), line("fri", "27T07:00"), line("mon", "30T10:00")), ["fri"])

    def test_direct_access(self):
        self.check(direct)

    def test_search_from_other_cup(self):
        self.check(search)


if __name__ == "__main__":
    unittest.main(verbosity=2)
