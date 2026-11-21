"""Offline checks for empty partner search windows and concurrent CUP offers."""

import asyncio
import os
import unittest
from datetime import datetime
from unittest.mock import patch

from city_sdk.city import LEDGER, understood

from test_cup_recovery import CITIZEN, HOSPITAL, PROCEDURE, Case, load_brain


class CupCapacityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.brain = load_brain()
        role = patch.dict(os.environ, {"CITY_ROLE": "booking_centre"})
        role.start()
        self.addCleanup(role.stop)

    async def test_372_no_capacity_skips_impossible_partner_window_and_keeps_local_alternative(self):
        # Arena 372: the CUP asked for earliest=24 Dec 02:15Z and deadline=23 Dec 16:06Z.
        case = Case(self.brain, "372-no-capacity")
        await case.open(local_free=1)
        offer_id = await case.accept_offer()
        case.add(
            LEDGER,
            f"slots page=1/1\nslot_id=S-LOCAL-ALTERNATIVE doctor_id=h2 facility={HOSPITAL} "
            f"procedure={PROCEDURE} agenda_date=2026-12-24T11:00:00Z agenda_day=thu free=1",
            conversation="ledger",
        )
        refusal = case.add(
            HOSPITAL,
            f"hold_refused ledger_code=NO_CAPACITY offer_id={offer_id} slot_id=S-LOCAL",
            conversation="facility",
        )
        now = datetime.fromisoformat("2026-12-23T16:15:00+00:00")
        deadline = datetime.fromisoformat("2026-12-23T16:06:00+00:00")
        with (
            patch.object(self.brain, "_agenda_now", return_value=now),
            patch.object(self.brain, "_true_deadline", return_value=deadline),
            patch.object(case, "search", wraps=case.search) as search,
        ):
            await case.turn(refusal)
        search.assert_not_awaited()
        self.assertEqual(len(case.out(CITIZEN, "cancel")), 1)
        (alternative,) = case.choices()
        self.assertEqual(alternative["slot_id"], "S-LOCAL-ALTERNATIVE")
        self.assertTrue(alternative.get("relaxed"))

    async def test_concurrent_needs_prioritize_distinct_slots_without_losing_options(self):
        first, second = (Case(self.brain, f"soft-spread-{i}") for i in range(2))
        send_started, allow_send = asyncio.Event(), asyncio.Event()
        send = first.post

        async def delayed_post(**kwargs):
            send_started.set()
            await allow_send.wait()
            return await send(**kwargs)

        with patch.object(first, "post", side_effect=delayed_post):
            first_turn = asyncio.create_task(first.open(local_free=1, second_local_slot=True))
            try:
                await asyncio.wait_for(send_started.wait(), timeout=1)
                await second.open(local_free=1, second_local_slot=True)
            finally:
                allow_send.set()
                await first_turn

        self.assertEqual([offer["slot_id"] for offer in first.choices()], ["S-LOCAL", "S-LOCAL-LATER"])
        self.assertEqual([offer["slot_id"] for offer in second.choices()], ["S-LOCAL-LATER", "S-LOCAL"])
        self.assertEqual(first.out(HOSPITAL, "confirm"), [])
        self.assertEqual(second.out(HOSPITAL, "confirm"), [])

    async def test_recent_single_slot_is_available_and_soft_preference_expires(self):
        first, second, third = (Case(self.brain, f"soft-spread-expiry-{i}") for i in range(3))
        clock = [1000.0]
        with patch.object(self.brain, "monotonic", lambda: clock[0]):
            await first.open(local_free=1, second_local_slot=True)
            await second.open(local_free=1)
            self.assertEqual([offer["slot_id"] for offer in second.choices()], ["S-LOCAL"])

            clock[0] += 151
            await third.open(local_free=1, second_local_slot=True)
            self.assertEqual([offer["slot_id"] for offer in third.choices()], ["S-LOCAL", "S-LOCAL-LATER"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
