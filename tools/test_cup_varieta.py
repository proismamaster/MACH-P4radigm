"""Le tre offerte del CUP coprono entrambi i generi di medico e più giorni.

Il cittadino ha preferenze nascoste di genere e di giorno e sceglie in un solo turno: nei percorsi
della console (21/11 04:03-04:18 UTC: 2440003, 2800002, 2860002, 255, 249, 2210004, 318) ha rifiutato
tutte e tre le offerte con reason=gender o reason=day. Giovedì e venerdì la fisiatria ha solo medici
uomini (h2, h3): "uno slot per giorno" dava tre offerte tutte maschili.
Dalla cartella della repo: python tools/test_cup_varieta.py  (riusa il Mailbox di test_cup_l5_vincoli.py)
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_cup_l5_vincoli as base  # noqa: E402
base.cup._CUP_OFFERS_PER_BATCH = 3  # questi test sono scritti per 3 offerte; le 5 si provano in test_cup_medici

GENDER = {"h1": "f", "h2": "m", "h3": "m"}


def mix(offers):
    return [(o["slot_id"], o["agenda_day"], GENDER[o["doctor_id"]]) for o in offers]


class VarietyTests(unittest.IsolatedAsyncioTestCase):
    async def test_both_genders_when_later_days_are_all_male(self):
        box = base.Mailbox("mix-gender", "D", [
            base.slot("wed-m", "h2", "25T10:30", "wed"),
            base.slot("wed-f", "h1", "25T12:00", "wed"),
            base.slot("thu-m", "h2", "26T12:00", "thu"),
            base.slot("fri-m", "h2", "27T10:30", "fri"),
        ])
        offers = await box.offer("lang=it")
        got = mix(offers)
        self.assertEqual(len(got), 3, got)
        self.assertEqual(got[0][0], "wed-m", got)                 # the first choice stays the same
        self.assertEqual({g for _, _, g in got}, {"m", "f"}, got)  # both genders
        self.assertGreaterEqual(len({d for _, d, _ in got}), 2, got)

    async def test_different_days_when_gender_is_stated(self):
        box = base.Mailbox("mix-days", "D", [
            base.slot("wed-1", "h2", "25T10:30", "wed"),
            base.slot("wed-2", "h2", "25T12:00", "wed"),
            base.slot("thu-1", "h2", "26T12:00", "thu"),
            base.slot("fri-1", "h2", "27T10:30", "fri"),
        ])
        offers = await box.offer("lang=it gender_preference=m")
        self.assertEqual([o["slot_id"] for o in offers], ["wed-1", "thu-1", "fri-1"])

    async def test_stated_days_are_kept(self):
        box = base.Mailbox("mix-stated", "D", [
            base.slot("wed-m", "h2", "25T10:30", "wed"),
            base.slot("wed-f", "h1", "25T12:00", "wed"),
            base.slot("thu-m", "h2", "26T12:00", "thu"),
        ])
        offers = await box.offer("lang=it days=wed")
        self.assertEqual({o["agenda_day"] for o in offers}, {"wed"})
        self.assertEqual({GENDER[o["doctor_id"]] for o in offers}, {"m", "f"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
