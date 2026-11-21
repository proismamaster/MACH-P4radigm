"""Messaggi del CUP al cittadino: ogni messaggio ha una frase con il passo successivo.

La review LLM della città dà a ogni agente, per ogni cittadino, -1 / 0 / +1 su proattività
("passività o freddezza -> -1"). Un messaggio fatto solo di token (`booking.receipt booking_id=...`,
`offer ... waiting_list=true`, `cancel ... reason=facility_cancelled`) è freddo e non dice cosa fare.
Dalla cartella della repo: python tools/test_cup_cortesia.py  (riusa il Mailbox di test_cup_l5_vincoli.py)
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_cup_l5_vincoli as base  # noqa: E402
from city_sdk.city import City, Need  # noqa: E402

cup = base.cup
ACTS = {"offer", "cancel", "booking.receipt", "consent", "data.request", "confirm"}


def sentence(text: str) -> str:
    """The words of ``text`` that are not act words or key=value tokens."""
    words = [w for line in text.splitlines() for w in line.split()]
    return " ".join(w for w in words if "=" not in w and w not in ACTS)


async def turn(box, sender, text):
    inbound = box.add(sender, text)
    city = City(index=box, history=box, messages=box, agent_id=base.AGENT, inbound=inbound)
    with patch.dict(os.environ, {"CITY_ROLE": "booking_centre"}), patch.object(cup, "_CUP_RING", ()):
        await cup.main(Need(message=inbound), city)


def to_citizen(box):
    return [row.text for row in box.sent if row.recipient == base.CITIZEN]


class CourtesyTests(unittest.IsolatedAsyncioTestCase):
    async def test_offers_end_with_a_next_step(self):
        box = base.Mailbox("offers", "B", [base.slot("fit", "h1", "24T09:00", "tue")])
        await box.offer("lang=en")
        msg = to_citizen(box)[-1]
        self.assertIn("offer", msg)
        self.assertIn("altr", sentence(msg.splitlines()[-1]).lower())  # "altre date / altri giorni"

    async def test_waiting_list_explains_what_happens(self):
        box = base.Mailbox("waiting", "P", [base.slot("fit", "h1", "24T09:00", "tue")])
        await box.offer("lang=en")
        msg = next(t for t in to_citizen(box) if "waiting_list=true" in t)
        self.assertGreater(len(sentence(msg).split()), 5, msg)

    async def test_receipt_and_facility_refusal_have_a_sentence(self):
        for label, reply, head in (
            ("ricevuta", "booking.receipt booking_id=bk-1 ledger_ref=L-1 offer_id={o} slot_id=fit", "booking.receipt"),
            ("rifiuto", "cancel offer_id={o} slot_id=fit reason=no_capacity", "cancel offer_id="),
        ):
            with self.subTest(label):
                box = base.Mailbox("flow-" + label, "B", [base.slot("fit", "h1", "24T09:00", "tue")])
                await box.offer("lang=en")
                offer = cup._offer_blocks(to_citizen(box)[-1])[0]
                await turn(box, base.CITIZEN, f"confirm offer_id={offer['offer_id']} consent_ref=cons-1")
                confirm = next(row for row in box.sent if row.text.startswith("confirm "))
                facility_offer = dict(w.split("=", 1) for w in confirm.text.split() if "=" in w)["offer_id"]
                await turn(box, confirm.recipient, reply.format(o=facility_offer))
                msg = next((t for t in reversed(to_citizen(box)) if t.startswith(head)), "")
                self.assertTrue(msg, f"{label}: nessun {head} al cittadino")
                self.assertGreater(len(sentence(msg.splitlines()[0]).split()), 5, msg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
