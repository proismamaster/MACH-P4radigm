"""Impostori (sabato dalle 10:00): il CUP chiede posti solo a strutture credibili dell'Index.

Il kit: "Livello 8 + impostori: agenti pensati per trarre in inganno la rete". Il CUP manda i criteri
di ricerca ai partner trovati con city.find e poi gira al cittadino le loro offerte: un impostore
che entra nella lista può proporre posti finti (attributo falso, prenotazione fantasma: -2).
Dalla cartella della repo: python tools/test_cup_impostori.py  (riusa il Mailbox di test_cup_l5_vincoli.py)
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_cup_l5_vincoli as base  # noqa: E402
from city_sdk.city import City, Need, Peer  # noqa: E402

cup = base.cup
SERVICE = "hospital.physiatry"


def peer(agent_id, role="hospital", caps=(SERVICE,), nca=True, reputation=0):
    return Peer(agent_id, role=role, capabilities=tuple(caps), no_clinical_advice=nca, reputation=reputation)


class IndexBox(base.Mailbox):
    def __init__(self, peers, *a, **k):
        super().__init__(*a, **k)
        self.peers = peers

    async def search(self, query):
        return list(self.peers)


_CASES = iter(range(10_000))


async def searched(peers):
    """Who the CUP sends its partner search to, when its own ASST has nothing."""
    box = IndexBox(peers, f"impostori-{next(_CASES)}", "B", [])
    inbound = box.add(base.CITIZEN, f"need.request prescription_number={base.RX} lang=en")
    city = City(index=box, history=box, messages=box, agent_id=base.AGENT, inbound=inbound)
    with patch.dict(os.environ, {"CITY_ROLE": "booking_centre"}), patch.object(cup, "_CUP_RING", ()), \
            patch.object(cup, "_CUP_PARTNER_REPLY_SECONDS", 0):
        await cup.main(Need(message=inbound), city)
    return [row.recipient for row in box.sent if row.text.startswith("need.request")]


class ImpostorTests(unittest.IsolatedAsyncioTestCase):
    async def test_wrong_role_with_the_right_capability_is_not_asked(self):
        asked = await searched([
            peer("agent:real-hospital"),
            peer("agent:fake-cup", role="booking_centre"),
            peer("agent:fake-gp", role="gp"),
        ])
        self.assertEqual(asked, ["agent:real-hospital"])

    async def test_card_without_no_clinical_advice_is_not_asked(self):
        asked = await searched([peer("agent:real-hospital"), peer("agent:no-declaration", nca=False)])
        self.assertEqual(asked, ["agent:real-hospital"])

    async def test_index_without_the_field_keeps_everyone(self):
        # If the Index never sends no_clinical_advice, the filter must not empty the list.
        asked = await searched([peer("agent:a", nca=False), peer("agent:b", nca=False)])
        self.assertEqual(sorted(asked), ["agent:a", "agent:b"])

    async def test_higher_reputation_first(self):
        asked = await searched([peer("agent:low", reputation=-5), peer("agent:high", reputation=40),
                                peer("agent:mid", reputation=3)])
        self.assertEqual(asked, ["agent:high", "agent:mid", "agent:low"])

    async def test_facility_role_still_accepted(self):
        asked = await searched([peer("agent:generic", role="facility")])
        self.assertEqual(asked, ["agent:generic"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
