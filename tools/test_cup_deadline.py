"""Rifiuto per deadline e "Which offer_id?": il CUP cerca entro il termine e non manda cancel senza id.

Uso, dalla cartella della repo: python tools/test_cup_deadline.py
Journey 8909110000710005, 8909110001220004, 8909110001240004 (export del 21/11): tre offerte di
fisiatria rifiutate con reason=deadline, poi il CUP offriva un'altra data tardiva; quando non c'era
nulla mandava `cancel reason=no_slots` senza offer_id e il cittadino rispondeva "Which offer_id?"
(in un caso anche partner_unavailable E no_slots nello stesso percorso).
Ora: dopo un rifiuto per deadline il CUP non allarga piu' la finestra di priorita'; il cancel porta
sempre un offer_id se c'e' un'offerta da annullare, altrimenti e' una frase semplice in italiano
senza parole d'atto; lo stesso avviso non si manda due volte.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from city_sdk.city import City, Need

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_cup_l5_vincoli as base  # noqa: E402  (riusa il Ledger finto del test L5, senza modificarlo)

cup = base.cup
base.cup._CUP_OFFERS_PER_BATCH = 3  # questi test sono scritti per 3 offerte; le 5 si provano in test_cup_medici
ACT_WORDS = {"cancel", "offer", "confirm", "consent", "booking.receipt", "need.request"}


def fri(identifier, hour):
    # venerdi' 27: oltre la finestra B (lunedi' 13:00 + 2 giorni feriali = mercoledi' 13:00)
    return base.slot(identifier, "asst-bicocca-h2", f"27T{hour}:00", "fri", live=True, extra="capacity=1")


class Run(base.Mailbox):
    async def turn(self, inbound):
        city = City(index=self, history=self, messages=self, agent_id=base.AGENT, inbound=inbound)
        with patch.dict(os.environ, {"CITY_ROLE": "booking_centre"}), patch.object(cup, "_CUP_RING", ()):
            await cup.main(Need(message=inbound), city)

    def to_citizen(self):
        return [row.text for row in self.sent if row.recipient == base.CITIZEN]


class DeadlineTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_slots_without_an_offer_is_plain_italian(self):
        box = Run("plain", "B", [])
        await box.turn(box.add(base.CITIZEN, f"need.request prescription_number={base.RX} lang=it"))
        said = box.to_citizen()
        self.assertEqual(len(said), 1)
        self.assertFalse(set(cup.words(said[0])) & ACT_WORDS, said[0])
        self.assertNotIn("reason=", said[0])

    async def test_the_same_notice_is_not_sent_twice(self):
        box = Run("twice", "B", [])
        await box.turn(box.add(base.CITIZEN, f"need.request prescription_number={base.RX} lang=it"))
        await box.turn(box.add(base.CITIZEN, f"need.request prescription_number={base.RX} lang=it"))
        self.assertEqual(len(box.to_citizen()), 1)

    def test_cancel_carries_the_open_offer_id(self):
        text = cup._no_slots_text("of-1", "no_slots")
        self.assertTrue(text.startswith("cancel offer_id=of-1 reason=no_slots "), text)
        self.assertFalse(set(cup.words(cup._no_slots_text("", "no_slots"))) & ACT_WORDS)

    def test_relaxed_alternative_does_not_widen_after_a_deadline_refusal(self):
        late = [fri("f1", "10").replace("agenda_date", "at").replace("agenda_day", "day")]
        now = cup._agenda_now(base.Mailbox("t", "B", []).rows)
        args = dict(now=now, lang="it", gender=None, procedure="VIS-FIS", priority="B")
        self.assertEqual([s["slot_id"] for s in cup._cup_relaxed(late, **args)], ["f1"])
        self.assertEqual(cup._cup_relaxed(late, widen=False, **args), [])
        self.assertFalse(cup._deadline_refused([], base.CITIZEN))

    async def test_after_a_deadline_refusal_the_window_is_not_widened_again(self):
        box = Run("deadline", "B", [fri("f1", "10"), fri("f2", "11"), fri("f3", "12"), fri("f4", "14")])
        await box.turn(box.add(base.CITIZEN, f"need.request prescription_number={base.RX} lang=it"))
        first = [o for text in box.to_citizen() for o in cup._offer_blocks(text)]
        self.assertEqual(len(first), 3, "la prima volta l'alternativa tardiva si propone")
        self.assertTrue(all(o.get("relaxed") == "true" for o in first))
        last = None
        for option in first:
            last = box.add(base.CITIZEN, f"cancel offer_id={option['offer_id']} reason=deadline")
        before = len(box.sent)
        await box.turn(last)
        later = [o for row in box.sent[before:] if row.recipient == base.CITIZEN
                 for o in cup._offer_blocks(row.text)]
        self.assertEqual(later, [], "rifiutate per deadline, le date oltre il termine non si riproppongono")


if __name__ == "__main__":
    unittest.main(verbosity=2)
