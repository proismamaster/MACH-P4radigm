"""Specialist: scadenze di priorità in giorni di AGENDA nelle risposte ai CUP di altre ASST.

Dalla cartella della repo: python tools/test_specialist_scadenze.py
Il kit (e19-rules.md, ADR-124): sabato e domenica di agenda non esistono. B = entro 2 giorni di agenda,
D = entro 5. Il codice usava `now + timedelta(days=2)` (giorni di calendario): di giovedì la finestra
di una B finiva sabato e ogni slot di lunedì veniva scartato (stesso errore già corretto in CUP e ospedale).
"""

import importlib.util
import os
import sys
import unittest
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("spec_agent", os.path.join(REPO, "asst", "specialist", "agent", "agent.py"))
agent = importlib.util.module_from_spec(spec)
sys.modules["spec_agent"] = agent
spec.loader.exec_module(agent)

ME = "agent:sh35cbsy287d"


def now(day, hour=8):
    return datetime(2026, 11, day, hour, 0, tzinfo=timezone.utc)


def line(slot_id, doctor, at):
    return (f"slot_id={slot_id} doctor_id=asst-bicocca-{doctor} facility={ME} procedure=VIS-CARD "
            f"at=2026-11-{at}:00.000Z free=1")


def found(priority, current, *rows, lang="it"):
    fields = {"priority": priority, "lang": lang}
    return [slot["slot_id"] for slot in agent._search_slots("\n".join(rows), now=current, me=ME, fields=fields)]


class AgendaDeadlineTests(unittest.TestCase):
    def test_b_on_thursday_reaches_monday(self):
        # s1 lavora lun-mer-ven. Giovedì 19 + 2 giorni di agenda = lunedì 23.
        self.assertEqual(found("B", now(19), line("fri", "s1", "20T14:30"), line("mon", "s1", "23T07:00")),
                         ["fri", "mon"])

    def test_b_on_friday_reaches_tuesday(self):
        # Venerdì 20 + 2 = martedì 24 alle 08:00: il lunedì c'è, il martedì dopo le 08:00 no.
        self.assertEqual(found("B", now(20), line("mon", "s1", "23T10:00"), line("tue", "s2", "24T07:00"),
                               line("late", "s2", "24T09:00")), ["mon", "tue"])

    def test_d_on_thursday_reaches_next_thursday(self):
        self.assertEqual(found("D", now(19), line("wed", "s1", "25T10:00"), line("next", "s1", "30T10:00")),
                         ["wed"])

    def test_b_midweek_unchanged(self):
        # Mercoledì 25 + 2 = venerdì 27: nessun fine settimana in mezzo.
        self.assertEqual(found("B", now(25), line("fri", "s1", "27T07:00"), line("mon", "s1", "30T10:00")),
                         ["fri"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
