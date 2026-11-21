"""Check the complete CUP citizen packet using realistic, synthetic Arena IDs."""

import os
import unittest
from unittest.mock import patch

from city_sdk.city import LEDGER, City, Message, Need, Peer


from test_cup_recovery import load_brain


CUP = "agent:cupfixture1"
LOCAL = "agent:localclinic1"
PARTNER = "agent:ringclinic01"
CITIZEN = "citizen:W01FIX-11-0002-000001"
RX = "prescription_number-000000000000000000AA"
SERVICE = "hospital.physiatry"
PROCEDURE = "VIS-FIS"
TIMES = ("09:00", "10:30", "12:00", "14:30", "16:00")


class Mailbox:
    def __init__(self, area):
        self.rows = []
        self.sent = []
        self.key = f"N-2026-11-02-890900000001-{area}"

    def add(self, sender, text, recipient=CUP):
        row = Message(type="chat", sender=sender, recipient=recipient, msg_id=f"m-{len(self.rows)}",
                      need_id=self.key, conversation_id=f"c-{self.key}", body={"text": text})
        self.rows.append(row)
        return row

    async def search(self, query):
        return [Peer(PARTNER, role="hospital", capabilities=(SERVICE,), no_clinical_advice=True)]

    async def history(self, *, peer, need_id):
        return [row for row in self.rows if peer is None or peer in (row.sender, row.recipient)]

    async def post(self, *, to, message_type, body, need_id, conversation_id, traceparent):
        assert message_type == "chat"
        assert need_id == self.key
        row = self.add(CUP, body["text"], to)
        self.sent.append(row)
        return row.msg_id

    async def turn(self, brain, row):
        city = City(index=self, history=self, messages=self, agent_id=CUP, inbound=row)
        await brain.main(Need(message=row), city)


async def run(brain, *, remote):
    area, facility = ("giambellino", PARTNER) if remote else ("bicocca", LOCAL)
    box = Mailbox(area)
    agenda = "2026-12-15T07:00:00.000Z"
    slot_lines, expected_expiry = [], {}
    for hhmm in TIMES:
        slot_id = f"W01QQQ-asst-{area}-h1-20261216-{hhmm.replace(':', '')}"
        expiry = (f"2026-12-16T{int(hhmm[:2]) - 1:02d}:{hhmm[3:]}:00.000Z" if remote
                  else f"2026-12-16T{hhmm}:00.000Z")
        expected_expiry[slot_id] = expiry
        slot_lines.append(
            f"slot_id={slot_id} doctor_id=asst-{area}-h1 facility={facility} procedure={PROCEDURE} "
            f"agenda_date=2026-12-16T{hhmm}:00.000Z agenda_day=wed capacity=1 expiry={expiry}"
        )

    inbound = box.add(CITIZEN, f"need.request prescription_number={RX} lang=en")
    box.add(LEDGER, f"prescription prescription_number={RX} state=issued procedure={PROCEDURE} priority=D")
    box.add(LEDGER, f"agenda agenda_now={agenda}")
    box.add(LEDGER, "\n".join(["slots page=1/1", *([] if remote else slot_lines)]))
    with patch.dict(os.environ, {"CITY_ROLE": "booking_centre"}), patch.object(brain, "_CUP_RING", ()):
        await box.turn(brain, inbound)
        if remote:
            (search,) = [row for row in box.sent if row.recipient == PARTNER]
            rid = brain.fields_of(search.text)["request_id"]
            response = "\n".join(
                f"offer offer_id=of-{slot_id} {line} doctor_lang=it/en doctor_gender=f request_id={rid}"
                for slot_id, line in zip(expected_expiry, slot_lines)
            )
            await box.turn(brain, box.add(PARTNER, response))

    (packet,) = [row for row in box.sent if row.recipient == CITIZEN and row.text.startswith("offer ")]
    offers = brain._offer_blocks(packet.text)
    lines = [line for line in packet.text.splitlines() if line.startswith("offer ")]
    assert len(lines) == len(offers)
    assert len(packet.text) <= 2000
    assert len({offer["offer_id"] for offer in offers}) == len(offers)
    assert all(offer["prescription_number"] == RX for offer in offers)
    assert all(offer["expiry"] == expected_expiry[offer["slot_id"]] for offer in offers)
    return len(offers)


class CupOfferPacketTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_sends_five_complete_local_offers_in_one_chat(self):
        self.assertEqual(await run(load_brain(), remote=False), 5)

    async def test_cross_asst_batch_preserves_complete_offers_under_body_limit(self):
        self.assertEqual(await run(load_brain(), remote=True), 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
