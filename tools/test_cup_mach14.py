"""Offline regressions for the CUP's MACH-1.4 partner round."""

import asyncio
import os
import unittest
from unittest.mock import patch

from city_sdk.city import understood

import test_cup_recovery as recovery
from test_cup_recovery import (
    APPOINTMENT, CITIZEN, LATER_APPOINTMENT, LATER_PARTNER_SLOT, PARTNER, PARTNER_OFFER,
    PARTNER_SLOT, PROCEDURE, Case,
)


class CupMach14Tests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.brain = recovery.load_brain()

    async def asyncSetUp(self):
        role = patch.dict(os.environ, {"CITY_ROLE": "booking_centre"})
        role.start()
        self.addCleanup(role.stop)

    async def test_mach14_search_closes_initial_round_before_late_matching_offer(self):
        case = Case(self.brain, "mach14-late-offer")
        clock = [1000.0]
        with patch.object(self.brain, "monotonic", lambda: clock[0]):
            await case.open(local_free=0)
            (search,) = case.out(PARTNER, "need.request")
            fields = understood(search).body
            self.assertIn("mach=1.4", search.text)
            self.assertIn("earliest=2026-11-23T16:00:00.000Z", search.text)
            request_id = fields["request_id"]

            # A reply for another request triggers a turn but does not finish this round.
            old_reply = "cancel reason=no_availability request_id=rq-obsolete"
            clock[0] += 14
            await case.turn(case.add(PARTNER, old_reply))
            self.assertFalse(any(row.recipient == CITIZEN for row in case.sent))
            clock[0] += 2
            await case.turn(case.add(PARTNER, old_reply))
            self.assertTrue(any(
                "Non ho trovato orari confermabili" in row.text for row in case.sent if row.recipient == CITIZEN
            ))

            await case.turn(case.add(
                PARTNER,
                f"offer offer_id={PARTNER_OFFER} slot_id={PARTNER_SLOT} doctor_id=doctor-h1 "
                f"facility={PARTNER} procedure={PROCEDURE} agenda_date={APPOINTMENT} request_id={request_id}",
                conversation="partner",
            ))
            self.assertEqual([offer["slot_id"] for offer in case.choices()], [PARTNER_SLOT])
            self.assertEqual(case.out(PARTNER, "confirm"), [], "A late offer cannot initiate a booking")

    async def test_mach14_wait_preserves_partial_offers_when_history_stalls(self):
        case = Case(self.brain, "mach14-stalled-history")
        original_history = case.history
        seen = False

        async def history(*, peer, need_id):
            nonlocal seen
            searches = case.out(PARTNER, "need.request")
            if searches:
                if seen:
                    await asyncio.Future()
                seen = True
                request_id = understood(searches[0]).body["request_id"]
                case.add(
                    PARTNER,
                    f"offer offer_id={PARTNER_OFFER} slot_id={PARTNER_SLOT} doctor_id=doctor-h1 "
                    f"facility={PARTNER} procedure={PROCEDURE} agenda_date={APPOINTMENT} request_id={request_id}",
                )
            return await original_history(peer=peer, need_id=need_id)

        with patch.object(case, "history", side_effect=history), patch.object(self.brain, "_CUP_PARTNER_REPLY_SECONDS", 0.05):
            await asyncio.wait_for(case.open(local_free=0), timeout=0.5)
        self.assertEqual([offer["slot_id"] for offer in case.choices()], [PARTNER_SLOT])
        self.assertEqual(case.out(PARTNER, "confirm"), [])

    async def test_mach14_late_reply_leaves_active_offer_in_place_until_declined(self):
        case = Case(self.brain, "mach14-active-choice")
        clock = [1000.0]
        with patch.object(self.brain, "monotonic", lambda: clock[0]):
            request_id = await case.receive_remote_offer()
            offer_id = case.choices()[0]["offer_id"]
            clock[0] += 16
            await case.turn(case.add(
                PARTNER,
                f"offer offer_id=of-{LATER_PARTNER_SLOT} slot_id={LATER_PARTNER_SLOT} doctor_id=doctor-h1 "
                f"facility={PARTNER} procedure={PROCEDURE} agenda_date={LATER_APPOINTMENT} request_id={request_id}",
                conversation="partner",
            ))
            self.assertEqual([offer["offer_id"] for offer in case.choices()], [offer_id])
            self.assertEqual(len(case.out(CITIZEN, "offer")), 1)
            await case.turn(case.add(CITIZEN, f"Non posso venire. cancel offer_id={offer_id} reason=deadline"))
        self.assertEqual([offer["slot_id"] for offer in case.choices()], [LATER_PARTNER_SLOT])
        self.assertEqual(case.out(PARTNER, "confirm"), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
