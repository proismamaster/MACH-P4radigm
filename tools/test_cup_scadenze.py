"""Scadenze di priorità in giorni di AGENDA (CUP). Dalla cartella della repo: python tools/test_cup_scadenze.py

Il kit (e19-rules.md, ADR-124): "Sabato e domenica di agenda non esistono: dopo il venerdì si riparte
dal lunedì successivo". B = entro 2 giorni di agenda, D = entro 5. Da giovedì, B arriva a lunedì.
Il codice dell'esempio usava `now + timedelta(days=2)` (giorni di calendario): di giovedì scartava
ogni slot di lunedì, di venerdì quasi tutto, e il CUP finiva sull'alternativa "rilassata".
Riusa il Mailbox di tools/test_cup_l5_vincoli.py.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_cup_l5_vincoli as base  # noqa: E402

THURSDAY = "2026-11-19T08:00:00Z"
FRIDAY = "2026-11-20T08:00:00Z"
WEDNESDAY = "2026-11-25T08:00:00Z"


def mailbox(name, priority, now, slots):
    base.NOW = now
    try:
        return base.Mailbox(name, priority, slots)
    finally:
        base.NOW = "2026-11-23T13:00:00Z"


def ids(offers):
    return [(offer["slot_id"], offer.get("relaxed")) for offer in offers]


class AgendaDeadlineTests(unittest.IsolatedAsyncioTestCase):
    async def test_b_on_thursday_reaches_monday(self):
        # Fisiatria in inglese: solo h1, lun-mer. Giovedì + 2 giorni di agenda = lunedì.
        box = mailbox("thu-b", "B", THURSDAY, [
            base.slot("monday", "h1", "23T07:00", "mon"),
            base.slot("tuesday", "h1", "24T09:00", "tue"),
        ])
        offers = await box.offer("lang=en")
        self.assertEqual(ids(offers), [("monday", None)])

    async def test_b_on_friday_reaches_tuesday(self):
        box = mailbox("fri-b", "B", FRIDAY, [
            base.slot("monday", "h1", "23T10:00", "mon"),
            base.slot("tuesday", "h1", "24T07:00", "tue"),
            base.slot("too-late", "h1", "24T09:00", "tue"),
        ])
        offers = await box.offer("lang=en")
        # Martedì e' oltre le 30 ore d'agenda (il weekend non conta), lunedi' no: martedi' prima.
        self.assertEqual(ids(offers), [("tuesday", None), ("monday", None)])

    async def test_d_on_thursday_reaches_next_thursday(self):
        box = mailbox("thu-d", "D", THURSDAY, [
            base.slot("wednesday", "h1", "25T10:00", "wed"),
            base.slot("next-week", "h1", "30T10:00", "mon"),
        ])
        offers = await box.offer("lang=en")
        self.assertEqual(ids(offers), [("wednesday", None)])

    async def test_b_midweek_unchanged(self):
        # Mercoledì + 2 = venerdì: nessun fine settimana, come prima.
        box = mailbox("wed-b", "B", WEDNESDAY, [
            base.slot("friday", "h2", "27T07:00", "fri"),
            base.slot("monday", "h1", "30T10:00", "mon"),
        ])
        offers = await box.offer("lang=it")
        self.assertEqual(ids(offers), [("friday", None)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
