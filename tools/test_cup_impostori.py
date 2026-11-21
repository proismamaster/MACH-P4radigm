"""Offline CUP regressions for Index compatibility and existing partner routes."""

import os
import unittest
from unittest.mock import patch

from city_sdk.city import Peer, understood

from test_cup_recovery import CITIZEN, CROSS_REF, OLD_RX, PROCEDURE, SERVICE, Case, load_brain


RARE = "agent:verified-rare"
WRONG_ROLE = "agent:incompatible-role"
WRONG_CAPABILITY = "agent:incompatible-capability"
CONFLICTING = "agent:conflicting-index-rows"
INCOMPLETE = "agent:legacy-incomplete"
UNCHECKED = "agent:unknown-incomplete"
ATTESTED = "agent:verified-hospital"
LEGACY = "agent:legacy-hospital"
OTHER_SERVICE = "specialist_care.cardiology"


class CupImpostorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.brain = load_brain()
        role = patch.dict(os.environ, {"CITY_ROLE": "booking_centre"})
        role.start()
        self.addCleanup(role.stop)

    async def test_incompatible_index_peers_cannot_return_from_ring_or_learned_entries(self):
        case = Case(self.brain, "blocked-ring-and-cache")
        ring = [("ka", agent, "") for agent in (WRONG_ROLE, RARE, INCOMPLETE)]
        learned = {SERVICE: dict.fromkeys((WRONG_CAPABILITY, CONFLICTING))}
        peers = [
            Peer(WRONG_ROLE, role="gp", capabilities=(SERVICE,), no_clinical_advice=True),
            Peer(RARE, role="hospital", capabilities=(SERVICE,)),
            Peer(WRONG_CAPABILITY, role="hospital", capabilities=(OTHER_SERVICE,)),
            Peer(CONFLICTING, role="hospital", capabilities=(SERVICE,)),
            Peer(CONFLICTING, role="specialist", capabilities=(SERVICE,)),
            Peer(INCOMPLETE, role="", capabilities=(" ",)),
            Peer(UNCHECKED),
            Peer(LEGACY, role="facility", capabilities=(SERVICE,), reputation=50),
            Peer(ATTESTED, role="hospital", capabilities=(SERVICE,), no_clinical_advice=True, reputation=5),
            Peer("agent: invalid-id", role="hospital", capabilities=(SERVICE,)),
        ]
        with (
            patch.object(self.brain, "_CUP_RING", ring),
            patch.object(self.brain, "_PARTNER_GOOD", learned),
            patch.object(case, "search", return_value=peers) as find,
        ):
            await case.open(local_free=0, preferences="lang=ka")

        find.assert_awaited_once_with(SERVICE)
        searches = [row for row in case.sent if row.text.startswith("need.request ")]
        self.assertEqual([row.recipient for row in searches], [RARE, INCOMPLETE, ATTESTED])
        self.assertLessEqual(len(searches), self.brain._CUP_MAX_PARTNERS)
        for search in searches:
            self.assertEqual(understood(search).body["lang"], "ka")
            self.assertNotIn(CITIZEN, search.text)
            self.assertNotIn(OLD_RX, search.text)

    async def test_reputation_orders_compatible_discovery_and_missing_role_is_accepted(self):
        case = Case(self.brain, "rank-compatible")
        low, high = "agent:lower-reputation", "agent:higher-reputation"
        peers = [
            Peer(low, role="hospital", capabilities=(SERVICE,), reputation=3),
            Peer(high, role="", capabilities=(SERVICE,), reputation=10),
        ]
        with patch.object(self.brain, "_CUP_RING", ()), patch.object(case, "search", return_value=peers):
            await case.open(local_free=0)
        targets = [row.recipient for row in case.sent if row.text.startswith("need.request ")]
        self.assertEqual(targets, [high, low])

    async def test_existing_rare_language_offer_keeps_its_request_and_waits_for_consent(self):
        case = Case(self.brain, "rare-consent")
        with (
            patch.object(self.brain, "_CUP_RING", (("ka", RARE, ""),)),
            patch.object(case, "search", return_value=[]) as find,
        ):
            await case.open(local_free=0, preferences="lang=ka")
            (search,) = case.out(RARE, "need.request")
            request_id = understood(search).body["request_id"]
            await case.turn(case.add(
                RARE, f"offer offer_id=rare-offer slot_id=S-RARE doctor_id=asst-giambellino-h3 "
                f"facility={RARE} procedure={PROCEDURE} agenda_date=2026-11-24T10:30:00Z "
                f"doctor_lang=it/ka request_id={request_id}", conversation="partner",
            ))
            offer_id = await case.accept_offer()
            self.assertEqual(case.out(RARE, "confirm"), [])
            (prompt,) = case.out(CITIZEN, "consent")
            self.assertEqual(understood(prompt).body["purpose"], "cross_asst")
            await case.turn(case.add(
                CITIZEN, f"consent purpose=cross_asst offer_id={offer_id} consent_ref={CROSS_REF}",
            ))
            (confirmation,) = case.out(RARE, "confirm")
            self.assertEqual(understood(confirmation).body["request_id"], request_id)
        find.assert_awaited_once_with(SERVICE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
