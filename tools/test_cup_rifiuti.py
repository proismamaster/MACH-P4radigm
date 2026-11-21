"""Il CUP impara dai rifiuti `day` e `gender` e legge i giorni scritti a parole.

Uso, dalla cartella della repo: python tools/test_cup_rifiuti.py
Console 21/11 (percorsi 221, 255, 249, 244, 225, 210, 100002): il cittadino scrive nel testo "posso
venire solo lunedi' o mercoledi'" (mai days=), o solo "in alcuni giorni"; il genere del medico non e'
dichiarato. Il CUP offriva tre slot dello stesso giorno, il cittadino rifiutava con `cancel
offer_id=... reason=day` o `reason=gender`, e il CUP non ne teneva conto (o taceva): no_booking -1.
Ora: i giorni a parole contano; `reason=day` toglie il giorno di quell'offerta, `reason=gender` fa
scegliere il genere opposto a quello del medico rifiutato; senza giorni dichiarati la prima serie di
offerte copre giorni diversi.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from city_sdk.city import City, Message, Need

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_cup_l5_vincoli as base  # noqa: E402  (riusa il Ledger finto del test L5, senza modificarlo)

cup = base.cup
base.cup._CUP_OFFERS_PER_BATCH = 3  # questi test sono scritti per 3 offerte; le 5 si provano in test_cup_medici
AGENT, CITIZEN = base.AGENT, base.CITIZEN


def row(sender, text, n, recipient=""):
    return Message(type="chat", sender=sender, recipient=recipient, msg_id=f"m{n}", need_id="N-1",
                   body={"text": text})


def offer_text(offer_id, doctor, day):
    return (f"offer offer_id={offer_id} slot_id=S-{offer_id} doctor_id={doctor} facility={base.HOSPITAL} "
            f"procedure=VIS-FIS agenda_date=2026-11-24T10:00:00Z agenda_day={day} priority=D")


class ParsingTests(unittest.TestCase):
    def test_italian_day_names_in_the_text(self):
        chat = [row(CITIZEN, "Buongiorno, ginocchio mi fa male. Posso venire solo lunedì o mercoledì. "
                             "need.request lang=it service_type=hospital.physiatry", 1)]
        self.assertEqual(cup._cup_days(chat, CITIZEN), {"mon", "wed"})

    def test_unaccented_and_english_names(self):
        chat = [row(CITIZEN, "Posso venire solo martedi o giovedi", 1)]
        self.assertEqual(cup._cup_days(chat, CITIZEN), {"tue", "thu"})

    def test_days_token_still_wins_and_refusal_text_is_not_a_preference(self):
        chat = [row(CITIZEN, "need.request days=mon/fri lang=it", 1),
                row(CITIZEN, "non posso il martedì cancel offer_id=of-1 reason=deadline", 2)]
        self.assertEqual(cup._cup_days(chat, CITIZEN), {"mon", "fri"})

    def test_some_days_without_names_means_no_restriction(self):
        chat = [row(CITIZEN, "Il ginocchio mi fa male. Posso venire solo in alcuni giorni.", 1)]
        self.assertEqual(cup._cup_days(chat, CITIZEN), set())

    def test_day_refusal_removes_that_weekday(self):
        chat = [row(CITIZEN, "need.request lang=it", 1),
                row(AGENT, offer_text("of-1", "asst-bicocca-h1", "tue"), 2, CITIZEN),
                row(CITIZEN, "non mi va cancel offer_id=of-1 reason=day", 3)]
        self.assertEqual(cup._cup_days(chat, CITIZEN), {"mon", "wed", "thu", "fri"})
        chat[0] = row(CITIZEN, "need.request days=mon/tue/wed", 1)
        self.assertEqual(cup._cup_days(chat, CITIZEN), {"mon", "wed"})

    def test_gender_refusal_means_the_other_gender(self):
        def chat_for(doctor):
            return [row(CITIZEN, "need.request lang=it", 1),
                    row(AGENT, offer_text("of-1", doctor, "tue"), 2, CITIZEN),
                    row(CITIZEN, "no cancel offer_id=of-1 reason=gender", 3)]
        self.assertEqual(cup._gender(chat_for("asst-bicocca-h1"), CITIZEN), "m")  # h1 e' una dottoressa
        self.assertEqual(cup._gender(chat_for("asst-bicocca-h2"), CITIZEN), "f")  # h2 e' un medico
        stated = chat_for("asst-bicocca-h1")
        stated[0] = row(CITIZEN, "need.request gender_preference=f", 1)
        self.assertEqual(cup._gender(stated, CITIZEN), "f", "il genere dichiarato vince")
        both = chat_for("asst-bicocca-h1") + [
            row(AGENT, offer_text("of-2", "asst-bicocca-h2", "wed"), 4, CITIZEN),
            row(CITIZEN, "no cancel offer_id=of-2 reason=gender", 5)]
        self.assertIsNone(cup._gender(both, CITIZEN), "rifiuti di entrambi i generi: nessuna indicazione")


def day(identifier, doctor, when):
    weekday = {"24": "tue", "25": "wed", "26": "thu", "27": "fri"}[when[:2]]
    return base.slot(identifier, doctor, when, weekday, live=True, extra="capacity=1")


SLOTS = [
    day("h1-tue", "asst-bicocca-h1", "24T10:00"), day("h3-tue", "asst-bicocca-h3", "24T14:00"),
    day("h1-wed", "asst-bicocca-h1", "25T10:00"), day("h2-wed", "asst-bicocca-h2", "25T12:00"),
    day("h1-wed2", "asst-bicocca-h1", "25T14:00"),
    day("h2-thu", "asst-bicocca-h2", "26T10:00"), day("h3-thu", "asst-bicocca-h3", "26T12:00"),
    day("h2-fri", "asst-bicocca-h2", "27T10:00"),
]


class Run(base.Mailbox):
    async def turn(self, inbound):
        city = City(index=self, history=self, messages=self, agent_id=AGENT, inbound=inbound)
        with patch.dict(os.environ, {"CITY_ROLE": "booking_centre"}), patch.object(cup, "_CUP_RING", ()):
            await cup.main(Need(message=inbound), city)

    def batches(self):
        return [cup._offer_blocks(r.text) for r in self.sent
                if r.recipient == CITIZEN and cup.first_word(r.text) == "offer"]


def doctor(block):
    return block["doctor_id"].rsplit("-", 1)[-1]


class FlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_named_days_limit_the_offers(self):
        box = Run("named", "D", SLOTS)
        await box.turn(box.add(CITIZEN, f"Posso venire solo mercoledì o giovedì. need.request "
                                        f"prescription_number={base.RX} lang=it"))
        days = {o["agenda_day"] for b in box.batches() for o in b}
        self.assertTrue(days and days <= {"wed", "thu"}, days)

    async def test_first_batch_covers_different_days_when_none_are_named(self):
        box = Run("spread", "D", SLOTS)
        await box.turn(box.add(CITIZEN, f"Posso venire solo in alcuni giorni. need.request "
                                        f"prescription_number={base.RX} lang=it"))
        first = box.batches()[0]
        self.assertEqual(len({o["agenda_day"] for o in first}), len(first), [o["agenda_day"] for o in first])
        self.assertEqual(len(first), 3)

    async def test_after_gender_and_day_refusals_the_next_batch_changes_both(self):
        box = Run("learn", "D", SLOTS)
        await box.turn(box.add(CITIZEN, f"Posso venire solo in alcuni giorni. need.request "
                                        f"prescription_number={base.RX} lang=it"))
        first = box.batches()[0]
        reasons = {"asst-bicocca-h1": "gender"}
        last = None
        for o in first:
            reason = reasons.get(o["doctor_id"], "day")
            last = box.add(CITIZEN, f"no grazie cancel offer_id={o['offer_id']} reason={reason}")
        before = len(box.sent)
        await box.turn(last)
        later = [o for r in box.sent[before:] if r.recipient == CITIZEN for o in cup._offer_blocks(r.text)]
        self.assertTrue(later, "il CUP risponde ai rifiuti")
        self.assertTrue(all(doctor(o) in {"h2", "h3"} for o in later), [doctor(o) for o in later])
        refused_days = {o["agenda_day"] for o in first if o["doctor_id"] != "asst-bicocca-h1"}
        self.assertFalse({o["agenda_day"] for o in later} & refused_days, "non ripropone il giorno rifiutato")


if __name__ == "__main__":
    unittest.main(verbosity=2)
