"""Regressioni locali del CUP con SDK e registro simulato.

Eseguire dalla radice della repo con python tools/test_cup_recovery.py.
MACH_CUP_TEST_BRAIN consente di provare lo stesso scenario su un altro commit.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import unittest
from dataclasses import replace
from itertools import count
from pathlib import Path
from unittest.mock import patch

from city_sdk.city import LEDGER, CapError, City, Message, Need, Peer, understood


ROOT = Path(__file__).resolve().parents[1]
CUP = "agent:t01/booking_centre"
HOSPITAL = "agent:t01/hospital"
PARTNER = "agent:t02/hospital"
CITIZEN = "citizen:t01/c-0042"
OLD_RX = "prescription_number-OLD123"
NEW_RX = "prescription_number-NEW456"
SERVICE = "hospital.physiatry"
PROCEDURE = "VIS-FIS"
# At least 10 agenda hours after the fixture clock (07:00/08:00): nearer slots are never offered.
APPOINTMENT = "2026-11-23T19:00:00+01:00"
LATER_APPOINTMENT = "2026-11-23T20:00:00+01:00"
CROSS_REF = "cons-42-cross_asst"
# Plain refusal from Arena retry 1630002, after the cross_asst consent prompt.
CROSS_REFUSAL = "Ho il cuore che mi batte forte, sono preoccupato, ma preferirei non condividere troppi dati."
PARTNER_OFFER = "of-S-EXT"
PARTNER_SLOT = "S-EXT"
LATER_PARTNER_SLOT = "S-EXT-LATER"


def load_brain():
    source = os.environ.get("MACH_CUP_TEST_BRAIN") or ROOT / "asst/booking_centre/agent/agent.py"
    spec = importlib.util.spec_from_file_location("cup_recovery_brain", source)
    brain = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = brain
    spec.loader.exec_module(brain)
    brain._PULL_PAUSE = 0
    return brain


class Case:
    def __init__(self, brain, key):
        self.brain = brain
        self.need_id = f"N-2026-11-23-{key}"
        self.ids = count()
        self.history_rows = []
        self.hidden_from_history = set()
        self.sent = []

    def add(self, sender, text, recipient=CUP, *, conversation="citizen", message_type="chat", fields=None):
        message = Message(
            type=message_type,
            sender=sender,
            recipient=recipient,
            msg_id=f"M-{self.need_id}-{next(self.ids)}",
            need_id=self.need_id,
            conversation_id=f"{self.need_id}:{conversation}",
            body={"text": text} if fields is None else fields,
        )
        self.history_rows.append(message)
        return message

    async def search(self, query):
        return [
            Peer(HOSPITAL, role="facility", district=4, capabilities=(SERVICE,)),
            Peer(PARTNER, role="hospital", district=6, capabilities=(SERVICE,)),  # as the live Index reports it
        ]

    async def post(self, *, to, message_type, body, need_id, conversation_id, traceparent=None):
        assert message_type == "chat"
        assert need_id == self.need_id
        conversation = conversation_id.rsplit(":", 1)[-1]
        row = self.add(CUP, body["text"], to, conversation=conversation)
        self.sent.append(row)
        return row.msg_id

    async def history(self, *, peer, need_id):
        return [
            row
            for row in self.history_rows
            if row.msg_id not in self.hidden_from_history
            and (need_id is None or row.need_id == need_id)
            and (peer is None or peer in (row.sender, row.recipient))
        ]

    async def turn(self, message):
        city = City(index=self, messages=self, history=self, agent_id=CUP, inbound=message)
        await self.brain.main(Need(message=message), city)

    def out(self, recipient, act):
        return [
            row for row in self.sent
            if row.recipient == recipient and row.text.split(maxsplit=1)[0] == act
        ]

    def rx_reply(self, number, *, state="issued"):
        return self.add(
            LEDGER,
            f"prescription prescription_number={number} patient={CITIZEN} state={state} "
            f"procedure={PROCEDURE} priority=B",
            conversation="ledger",
        )

    async def open(self, local_free, *, second_local_slot=False, preferences="lang=it"):
        request = self.add(CITIZEN, f"need.request prescription_number={OLD_RX} {preferences}")
        self.rx_reply(OLD_RX)
        self.add(LEDGER, "agenda agenda_now=2026-11-23T07:00:00+01:00", conversation="ledger")
        slots = (
            f"slots page=1/1\nslot_id=S-LOCAL doctor_id=doctor-h1 facility={HOSPITAL} "
            f"procedure={PROCEDURE} at={APPOINTMENT} day=mon free={local_free}"
        )
        if second_local_slot:
            slots += (
                f"\nslot_id=S-LOCAL-LATER doctor_id=doctor-h1 facility={HOSPITAL} "
                f"procedure={PROCEDURE} at={LATER_APPOINTMENT} day=mon free=1"
            )
        self.add(LEDGER, slots, conversation="ledger")
        await self.turn(request)

    def choices(self):
        message = self.out(CITIZEN, "offer")[-1]
        return [
            understood(replace(message, body={"text": line})).body
            for line in message.text.splitlines()
            if line.startswith("offer ")
        ]

    async def accept_offer(self):
        offer_id = self.choices()[0]["offer_id"]
        await self.turn(self.add(CITIZEN, f"confirm offer_id={offer_id} consent_ref=cons-42-booking"))
        return offer_id

    async def book_local(self, *, booking_id="BK-1"):
        offer_id = await self.accept_offer()
        await self.turn(self.add(
            HOSPITAL, f"booking.receipt booking_id={booking_id} ledger_ref=LR-{booking_id}", conversation="facility",
        ))
        assert understood(self.out(CITIZEN, "booking.receipt")[-1]).body["booking_id"] == booking_id
        return offer_id

    async def receive_remote_offer(self, *, second_partner_slot=False, preferences="lang=it"):
        await self.open(local_free=0, preferences=preferences)
        (request,) = self.out(PARTNER, "need.request")
        request_id = understood(request).body["request_id"]

        options = (
            f"offer offer_id={PARTNER_OFFER} slot_id={PARTNER_SLOT} doctor_id=doctor-h1 "
            f"facility={PARTNER} procedure={PROCEDURE} agenda_date={APPOINTMENT} agenda_day=mon "
            f"expiry={APPOINTMENT} request_id={request_id} priority=B"
        )
        if second_partner_slot:
            options += (
                f"\noffer offer_id=of-{LATER_PARTNER_SLOT} slot_id={LATER_PARTNER_SLOT} doctor_id=doctor-h1 "
                f"facility={PARTNER} procedure={PROCEDURE} agenda_date={LATER_APPOINTMENT} agenda_day=mon "
                f"expiry={LATER_APPOINTMENT} request_id={request_id} priority=B"
            )
        await self.turn(self.add(PARTNER, options, conversation="partner"))
        return request_id

    async def reach_remote_consent(self, *, second_partner_slot=False, preferences="lang=it"):
        request_id = await self.receive_remote_offer(second_partner_slot=second_partner_slot, preferences=preferences)
        offer_id = await self.accept_offer()
        (prompt,) = self.out(CITIZEN, "consent")
        assert understood(prompt).body["purpose"] == "cross_asst"
        assert not self.out(PARTNER, "confirm")
        return offer_id, request_id

    def renewal_requests(self):
        return [
            row for row in self.out(CITIZEN, "data.request")
            if understood(row).body.get("purpose") == "prescription_renewal"
        ]


class CupRecoveryTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.brain = load_brain()

    async def asyncSetUp(self):
        self.brain._CUP_RECENT_OFFERS.clear()
        role = patch.dict(os.environ, {"CITY_ROLE": "booking_centre"})
        role.start()
        self.addCleanup(role.stop)

    async def test_post_receipt_cancellation_ignores_unrelated_or_conflicting_events(self):
        for index, (sender, template) in enumerate((
            (PARTNER, "cancel booking_id=BK-1 slot_id=S-LOCAL"),
            (PARTNER, "fault.cancel booking_id=BK-1 slot_id=S-LOCAL"),
            (HOSPITAL, "cancel reason=facility_cancelled"),
            (HOSPITAL, "cancel offer_id={offer_id} reason=facility_cancelled"),
            (HOSPITAL, "cancel offer_id={offer_id} slot_id=S-LOCAL reason=expired"),
            (HOSPITAL, "cancel booking_id=BK-1 slot_id=S-OTHER"),
            (HOSPITAL, "cancel booking_id=BK-OTHER slot_id=S-LOCAL"),
            (HOSPITAL, "cancel booking_id=BK-1 offer_id=of-other"),
            (LEDGER, "fault.cancel booking_id=BK-OTHER slot_id=S-LOCAL"),
        )):
            with self.subTest(sender=sender, cancel=template):
                case = Case(self.brain, f"booked-unrelated-cancel-{index}")
                await case.open(local_free=1, second_local_slot=True)
                offer_id = await case.book_local()
                mark = len(case.sent)
                await case.turn(case.add(sender, template.format(offer_id=offer_id), conversation="facility"))
                self.assertEqual(case.sent[mark:], [], "An unrelated cancellation must leave the booking intact")

    async def test_post_receipt_cancellation_accepts_facility_combined_rebook_message(self):
        case = Case(self.brain, "booked-facility-rebook")
        await case.open(local_free=1, second_local_slot=True)
        offer_id = await case.book_local()
        cancel = (
            f"cancel reason=facility_cancelled booking_id=BK-1 offer_id={offer_id} slot_id=S-LOCAL\n"
            f"offer offer_id=of-facility-new slot_id=S-LOCAL-LATER agenda_date={LATER_APPOINTMENT}"
        )
        await case.turn(case.add(HOSPITAL, cancel, conversation="facility"))

        (notice,) = case.out(CITIZEN, "cancel")
        self.assertEqual(understood(notice).body["booking_id"], "BK-1")
        self.assertEqual([offer["slot_id"] for offer in case.choices()], ["S-LOCAL-LATER"])
        await case.turn(case.add(HOSPITAL, cancel, conversation="facility"))
        self.assertEqual(len(case.out(CITIZEN, "cancel")), 1, "Duplicate fault cannot reopen the booking twice")

    async def test_post_receipt_cancellation_accepts_typed_city_fault_after_earlier_rebooking(self):
        case = Case(self.brain, "booked-city-fault")
        await case.open(local_free=1, second_local_slot=True)
        await case.book_local()
        await case.turn(case.add(HOSPITAL, "cancel booking_id=BK-1", conversation="facility"))
        await case.book_local(booking_id="BK-2")
        mark = len(case.sent)
        await case.turn(case.add(HOSPITAL, "cancel booking_id=BK-1", conversation="facility"))
        await case.turn(case.add(
            LEDGER, "", conversation="ledger", message_type="fault.cancel",
            fields={"booking_id": "BK-2", "slot_id": ["S-OTHER"]},
        ))
        self.assertEqual(case.sent[mark:], [], "A replay or malformed field cannot cancel the new booking")

        await case.turn(case.add(
            LEDGER, "", conversation="ledger", message_type="fault.cancel",
            fields={"booking_id": "BK-2", "reason": "facility_cancelled"},
        ))
        self.assertEqual(
            [understood(row).body.get("booking_id") for row in case.out(CITIZEN, "cancel")
             if "booking_id=" in row.text],
            ["BK-1", "BK-2"],
        )

    async def test_post_receipt_cancellation_accepts_city_fault_with_matching_slot(self):
        case = Case(self.brain, "booked-city-slot-fault")
        await case.open(local_free=1, second_local_slot=True)
        await case.book_local()
        await case.turn(case.add(LEDGER, "fault.cancel slot_id=S-LOCAL", conversation="ledger"))

        (notice,) = case.out(CITIZEN, "cancel")
        self.assertEqual(understood(notice).body["booking_id"], "BK-1")
        self.assertEqual([offer["slot_id"] for offer in case.choices()], ["S-LOCAL-LATER"])

    async def test_p1_facility_cancellation_requires_new_verified_prescription(self):
        case = Case(self.brain, "facility-expiry")
        await case.open(local_free=1, second_local_slot=True)
        self.assertEqual([offer["slot_id"] for offer in case.choices()], ["S-LOCAL", "S-LOCAL-LATER"])
        offer_id = await case.accept_offer()
        self.assertEqual(len(case.out(HOSPITAL, "confirm")), 1)

        expired = f"cancel offer_id={offer_id} slot_id=S-LOCAL reason=PRESCRIPTION_EXPIRED"
        await case.turn(case.add(HOSPITAL, expired, conversation="facility"))
        self.assertEqual(len(case.renewal_requests()), 1, "CUP must ask for renewal after facility expiry")
        await case.turn(case.add(HOSPITAL, expired, conversation="facility"))
        await case.turn(case.add(CITIZEN, f"need.request prescription_number={OLD_RX} lang=it"))
        await case.turn(case.add(CITIZEN, f"confirm offer_id={offer_id} consent_ref=cons-42-booking"))
        self.assertEqual(len(case.renewal_requests()), 1, "Repeated expiry must not prompt twice")
        self.assertEqual(len(case.out(HOSPITAL, "confirm")), 1, "The expired prescription must not be retried")
        self.assertEqual(len(case.out(CITIZEN, "offer")), 1, "No further offers with the expired prescription")

        mark = len(case.sent)
        await case.turn(case.add(CITIZEN, f"need.request prescription_number={NEW_RX} lang=it"))
        lookups = [
            row for row in case.sent[mark:] if row.recipient == LEDGER
            and row.text.startswith("prescription ")
            and understood(row).body.get("prescription_number") == NEW_RX
        ]
        self.assertEqual(len(lookups), 1, "The Ledger must verify the replacement prescription")
        self.assertEqual(len(case.out(CITIZEN, "offer")), 1, "Wait for the Ledger before sending a new offer")
        await case.turn(case.rx_reply(OLD_RX))
        self.assertEqual(len(case.out(CITIZEN, "offer")), 1, "A reply about the old prescription cannot unlock an offer")

        await case.turn(case.rx_reply(NEW_RX))
        after_renewal = case.sent[case.sent.index(case.renewal_requests()[0]) + 1:]
        reads = [row.text for row in after_renewal if row.recipient == LEDGER]
        self.assertIn("agenda", reads, "After a renewal the agenda read before it is stale: ask again")
        self.assertTrue(any(text.startswith("world ") for text in reads), "After a renewal ask the slots again")
        self.assertEqual(len(case.out(CITIZEN, "offer")), 1, "No offer from the stale slots read before the renewal")

        # Meanwhile S-LOCAL-LATER was taken: the fresh read has only S-NEW.
        case.add(LEDGER, "agenda agenda_now=2026-11-23T08:00:00+01:00", conversation="ledger")
        fresh_slots = case.add(
            LEDGER,
            f"slots page=1/1\nslot_id=S-NEW doctor_id=doctor-h1 facility={HOSPITAL} "
            f"procedure={PROCEDURE} at={LATER_APPOINTMENT} day=mon free=1",
            conversation="ledger",
        )
        await case.turn(fresh_slots)
        _, new_offer = case.out(CITIZEN, "offer")
        self.assertEqual(understood(new_offer).body.get("prescription_number"), NEW_RX)
        self.assertEqual([offer["slot_id"] for offer in case.choices()], ["S-NEW"])
        await case.accept_offer()
        previous, latest = case.out(HOSPITAL, "confirm")
        self.assertEqual(understood(previous).body.get("prescription_number"), OLD_RX)
        self.assertEqual(understood(latest).body.get("prescription_number"), NEW_RX)
        self.assertEqual(understood(latest).body.get("slot_id"), "S-NEW")

    async def test_p1_ledger_expiry_in_same_need_requests_renewal_once(self):
        case = Case(self.brain, "ledger-expiry")
        original = case.add(CITIZEN, f"need.request prescription_number={OLD_RX} lang=it")
        await case.turn(original)
        await asyncio.gather(
            case.turn(case.rx_reply(OLD_RX, state="expired")),
            case.turn(case.rx_reply(OLD_RX, state="expired")),
        )
        self.assertEqual(len(case.renewal_requests()), 1, "Ledger expiry must redirect the citizen exactly once")
        self.assertEqual(case.out(CITIZEN, "offer"), [])
        self.assertEqual(case.out(HOSPITAL, "confirm"), [])

    async def test_cross_asst_accepts_consent_after_natural_language_preamble(self):
        case = Case(self.brain, "consent-preamble")
        await case.reach_remote_consent()
        await case.turn(case.add(CITIZEN, f"need.request prescription_number={OLD_RX} lang=it"))
        self.assertEqual(case.out(CITIZEN, "cancel"), [], "Retrying the booking request is not a refusal")
        await case.turn(case.add(
            CITIZEN, f"Certo, va bene. consent purpose=cross_asst consent_ref={CROSS_REF}"
        ))
        confirmations = case.out(PARTNER, "confirm")
        self.assertEqual(len(confirmations), 1, "The consent act need not be the first word")
        self.assertEqual(understood(confirmations[0]).body["consent_ref"], CROSS_REF)
        self.assertEqual(case.out(CITIZEN, "cancel"), [])

    async def test_cross_asst_refusal_immediately_offers_verified_local_slot(self):
        for relaxed in (False, True):
            with self.subTest(outside_priority_window=relaxed):
                case = Case(self.brain, f"1630002-consent-refusal-local-{relaxed}")
                offer_id, _ = await case.reach_remote_consent(preferences="lang=en gender_preference=f")
                await case.turn(case.add(
                    CITIZEN, f"consent purpose=report_sharing consent_ref={CROSS_REF} offer_id={offer_id}",
                ))
                await case.turn(case.add(
                    CITIZEN, f"consent purpose=cross_asst consent_ref={CROSS_REF} offer_id=of-wrong",
                ))
                self.assertEqual(case.out(CITIZEN, "cancel"), [])
                self.assertEqual(case.out(PARTNER, "confirm"), [])

                slot_at = "2026-11-30T13:00:00+01:00" if relaxed else LATER_APPOINTMENT
                case.add(
                    LEDGER,
                    f"slots page=1/1\nslot_id=S-LOCAL-FREE doctor_id=doctor-h1 facility={HOSPITAL} "
                    f"procedure={PROCEDURE} at={slot_at} day=mon free=1\n"
                    f"slot_id=S-LOCAL-WRONG doctor_id=doctor-h3 facility={HOSPITAL} "
                    f"procedure={PROCEDURE} at=2026-11-24T13:00:00+01:00 day=tue free=1",
                    conversation="ledger",
                )
                await case.turn(case.add(CITIZEN, CROSS_REFUSAL))
                self.assertEqual(len(case.out(CITIZEN, "offer")), 2, "The refusal must immediately restart the local search")
                (local_offer,) = case.choices()
                self.assertEqual(local_offer["slot_id"], "S-LOCAL-FREE")
                self.assertEqual(local_offer["facility"], HOSPITAL)
                self.assertEqual(local_offer.get("relaxed"), True if relaxed else None)
                self.assertEqual(case.out(HOSPITAL, "confirm"), [], "A local offer still needs a citizen confirmation")

                await case.turn(case.add(
                    CITIZEN, f"consent purpose=cross_asst consent_ref={CROSS_REF} offer_id={offer_id}",
                ))
                self.assertEqual(case.out(PARTNER, "confirm"), [])
                await case.accept_offer()
                (confirmation,) = case.out(HOSPITAL, "confirm")
                self.assertEqual(understood(confirmation).body["slot_id"], "S-LOCAL-FREE")

    async def test_cross_asst_refusal_does_not_resurface_partner_offers(self):
        case = Case(self.brain, "consent-refusal-no-local-slot")
        partner_choice, _ = await case.reach_remote_consent(second_partner_slot=True)
        search_count = len(case.out(PARTNER, "need.request"))

        await case.turn(case.add(CITIZEN, CROSS_REFUSAL))
        await case.turn(case.add(CITIZEN, CROSS_REFUSAL))
        await case.turn(case.add(CITIZEN, f"confirm offer_id={partner_choice} consent_ref=cons-42-booking"))
        self.assertEqual(len(case.out(CITIZEN, "consent")), 1)
        self.assertEqual(len(case.out(PARTNER, "need.request")), search_count)
        self.assertEqual(len(case.out(CITIZEN, "offer")), 1, "After the refusal, no more partner offers")
        self.assertEqual(case.out(PARTNER, "confirm"), [])

    async def test_cross_asst_refusal_blocks_late_consent_if_acknowledgment_cannot_be_sent(self):
        case = Case(self.brain, "consent-refusal-ack-unavailable")
        offer_id, _ = await case.reach_remote_consent()
        with patch.object(case, "post", side_effect=CapError("UPSTREAM_TIMEOUT")):
            await case.turn(case.add(CITIZEN, CROSS_REFUSAL))
        self.assertEqual(case.out(CITIZEN, "cancel"), [])

        await case.turn(case.add(
            CITIZEN, f"consent purpose=cross_asst consent_ref={CROSS_REF} offer_id={offer_id}",
        ))
        self.assertEqual(case.out(PARTNER, "confirm"), [], "The refusal was recorded even when its reply could not be sent")

    async def test_cross_asst_declined_offer_does_not_accept_late_confirmation(self):
        for hidden in (False, True):
            with self.subTest(offer_missing_from_relay_history=hidden):
                case = Case(self.brain, f"declined-offer-{hidden}")
                await case.receive_remote_offer()
                offer_id = case.choices()[0]["offer_id"]
                if hidden:
                    case.hidden_from_history.add(case.out(CITIZEN, "offer")[-1].msg_id)
                await case.turn(case.add(CITIZEN, f"Non posso venire. cancel offer_id={offer_id} reason=deadline"))
                await case.turn(case.add(CITIZEN, f"confirm offer_id={offer_id} consent_ref=cons-42-booking"))
                self.assertEqual(case.out(CITIZEN, "consent"), [], "A declined offer cannot start a new consent flow")
                self.assertEqual(case.out(PARTNER, "confirm"), [])

    async def test_cross_asst_history_keeps_send_order_when_one_search_is_missing(self):
        case = Case(self.brain, "partial-relay-history")
        await case.receive_remote_offer()
        # A search after the first one of the turn (the partner from city.find is now asked first).
        search = [row for row in case.sent if row.text.startswith("need.request")][1]
        case.hidden_from_history.add(search.msg_id)

        relay_rows = await case.history(peer=None, need_id=case.need_id)
        merged = self.brain._cup_history(relay_rows, self.brain._sent(case.need_id), CUP, case.need_id)
        self.assertEqual([row.msg_id for row in merged], [row.msg_id for row in case.history_rows])

    async def test_cross_asst_last_decline_reopens_search_for_alternative(self):
        case = Case(self.brain, "last-offer-declined")
        request_id = await case.receive_remote_offer()
        offer_id = case.choices()[0]["offer_id"]
        await case.turn(case.add(CITIZEN, f"Non posso venire. cancel offer_id={offer_id} reason=deadline"))

        await case.turn(case.add(
            PARTNER,
            f"offer offer_id=of-{LATER_PARTNER_SLOT} slot_id={LATER_PARTNER_SLOT} doctor_id=doctor-h1 "
            f"facility={PARTNER} procedure={PROCEDURE} agenda_date={LATER_APPOINTMENT} request_id={request_id}",
            conversation="partner",
        ))
        self.assertEqual(len(case.out(CITIZEN, "offer")), 2, "After the last decline, offer a valid alternative")
        self.assertEqual([offer["slot_id"] for offer in case.choices()], [LATER_PARTNER_SLOT])

    async def test_cross_asst_withdrawal_while_awaiting_consent_blocks_confirm(self):
        case = Case(self.brain, "withdrawal")
        offer_id, request_id = await case.reach_remote_consent()
        await case.turn(case.add(
            PARTNER,
            f"cancel offer_id={PARTNER_OFFER} slot_id={PARTNER_SLOT} request_id={request_id} "
            "reason=facility_cancelled",
            conversation="partner",
        ))
        cancellations = case.out(CITIZEN, "cancel")
        await case.turn(case.add(
            CITIZEN, f"consent purpose=cross_asst offer_id={offer_id} consent_ref={CROSS_REF}"
        ))
        self.assertEqual(case.out(PARTNER, "confirm"), [], "A withdrawn slot must never receive the patient's data")
        self.assertTrue(
            any(understood(row).body.get("offer_id") == offer_id for row in cancellations),
            "The citizen should be told which offer was withdrawn",
        )

    async def test_confirm_without_facility_answer_is_resent_then_released(self):
        """3590002: citizen confirmed, the facility never answered for 32 minutes."""
        case = Case(self.brain, "confirm-silence")
        await case.open(local_free=1, second_local_slot=True)
        clock = [1000.0]
        with patch.object(self.brain, "monotonic", lambda: clock[0]):
            offer_id = await case.accept_offer()
            self.assertEqual(len(case.out(HOSPITAL, "confirm")), 1)
            clock[0] += 60
            await case.turn(case.add(CITIZEN, f"confirm offer_id={offer_id} consent_ref=cons-42-booking"))
            self.assertEqual(len(case.out(HOSPITAL, "confirm")), 1, "Too early: no resend yet")
            clock[0] += 200
            await case.turn(case.add(CITIZEN, f"confirm offer_id={offer_id} consent_ref=cons-42-booking"))
            self.assertEqual(len(case.out(HOSPITAL, "confirm")), 2, "Silent facility: the confirm is sent again once")
            self.assertEqual(case.out(CITIZEN, "cancel"), [])
            clock[0] += 200
            await case.turn(case.add(CITIZEN, f"confirm offer_id={offer_id} consent_ref=cons-42-booking"))
            self.assertEqual(len(case.out(HOSPITAL, "confirm")), 2, "Never a third confirm")
            cancels = case.out(CITIZEN, "cancel")
            self.assertEqual(len(cancels), 1, "Still silent: the citizen is released and the search restarts")
            self.assertIn(f"offer_id={offer_id}", cancels[0].text)

    async def test_cross_asst_withdrawal_without_request_id_keeps_other_slot(self):
        case = Case(self.brain, "withdrawal-alternative")
        offer_id, _ = await case.reach_remote_consent(second_partner_slot=True)
        withdrawal = f"cancel offer_id={PARTNER_OFFER} slot_id={PARTNER_SLOT} reason=facility_cancelled"
        await case.turn(case.add(HOSPITAL, withdrawal, conversation="facility"))
        await case.turn(case.add(
            PARTNER,
            f"cancel offer_id={PARTNER_OFFER} slot_id={LATER_PARTNER_SLOT} reason=facility_cancelled",
            conversation="partner",
        ))
        self.assertEqual(case.out(CITIZEN, "cancel"), [], "A different sender or slot cannot withdraw this offer")

        await case.turn(case.add(PARTNER, withdrawal, conversation="partner"))
        cancellations = case.out(CITIZEN, "cancel")
        self.assertEqual(len(cancellations), 1, "A matching withdrawal need not repeat the request ID")
        self.assertEqual(understood(cancellations[0]).body["offer_id"], offer_id)
        self.assertEqual([offer["slot_id"] for offer in case.choices()], [LATER_PARTNER_SLOT])

        await case.turn(case.add(
            CITIZEN, f"consent purpose=cross_asst offer_id={offer_id} consent_ref={CROSS_REF}"
        ))
        self.assertEqual(case.out(PARTNER, "confirm"), [])
        alternative = await case.accept_offer()
        await case.turn(case.add(
            CITIZEN, f"consent purpose=cross_asst offer_id={alternative} consent_ref=cons-43-cross_asst"
        ))
        confirmation, = case.out(PARTNER, "confirm")
        self.assertEqual(understood(confirmation).body["slot_id"], LATER_PARTNER_SLOT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
