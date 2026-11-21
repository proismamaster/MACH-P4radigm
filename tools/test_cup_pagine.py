"""Il CUP legge il catalogo oltre la pagina 8, si ferma al primo lotto valido e non scansiona all'infinito.

Uso, dalla cartella della repo: python tools/test_cup_pagine.py
Prima: _MAX_PAGE = 8 e un posto libero sulla pagina 9 non veniva mai chiesto (journey con 79 posti
effettivi e nessuna offerta). Ora: fino a 20 pagine e circa 60 secondi reali per caso.
"""

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from city_sdk.city import LEDGER, City, Need

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import test_cup_l5_vincoli as base  # noqa: E402  (riusa il Ledger finto del test L5, senza modificarlo)

cup = base.cup


class PagedMailbox(base.Mailbox):
    """Il Ledger risponde a `world procedure=... page=N` con la pagina N del catalogo."""

    def __init__(self, name, total, valid_page, seconds_per_page=0.0):
        super().__init__(name, "B", [])
        self.rows.pop()  # niente pagina 1 vuota di partenza: la chiede il CUP
        self.total = total
        self.valid_page = valid_page
        self.asked = []
        self.clock = 1000.0
        self.seconds_per_page = seconds_per_page

    async def post(self, *, to, message_type, body, need_id, conversation_id, traceparent):
        mid = await super().post(to=to, message_type=message_type, body=body, need_id=need_id,
                                 conversation_id=conversation_id, traceparent=traceparent)
        text = body["text"]
        if to == LEDGER and text.startswith("world "):
            page = int(text.rsplit("page=", 1)[1])
            self.asked.append(page)
            self.clock += self.seconds_per_page
            lines = []
            if page == self.valid_page:
                lines.append(base.slot("far-page", "asst-bicocca-h1", "25T10:00", "wed", live=True,
                                       extra="capacity=1"))
            self.add(LEDGER, f"slots page={page}/{self.total}\n" + "\n".join(lines))
        return mid

    async def run(self):
        inbound = self.add(base.CITIZEN, f"need.request prescription_number={base.RX} lang=it")
        city = City(index=self, history=self, messages=self, agent_id=base.AGENT, inbound=inbound)
        with patch.dict(os.environ, {"CITY_ROLE": "booking_centre"}), \
                patch.object(cup, "_CUP_RING", ()), patch.object(cup, "monotonic", lambda: self.clock), \
                patch.object(cup, "_PULL_PAUSE", 0.0):
            await cup.main(Need(message=inbound), city)
        return [o for row in self.sent if row.recipient == base.CITIZEN for o in cup._offer_blocks(row.text)]


class PagingTests(unittest.IsolatedAsyncioTestCase):
    async def test_page_nine_is_read_and_offered(self):
        mailbox = PagedMailbox("page9", total=9, valid_page=9)
        offers = await mailbox.run()
        self.assertEqual([o["slot_id"] for o in offers], ["far-page"])
        self.assertEqual(mailbox.asked.count(9), 1, "la pagina 9 si chiede una volta sola")
        self.assertEqual(mailbox.asked, list(range(1, 10)), "una pagina alla volta, in ordine")

    async def test_stops_at_the_first_valid_page(self):
        mailbox = PagedMailbox("first-valid", total=15, valid_page=3)
        offers = await mailbox.run()
        self.assertEqual([o["slot_id"] for o in offers], ["far-page"])
        self.assertEqual(max(mailbox.asked), 3, "dopo il primo lotto valido non chiede altre pagine")

    async def test_never_more_than_twenty_pages(self):
        mailbox = PagedMailbox("twenty", total=40, valid_page=30)
        await mailbox.run()
        self.assertEqual(max(mailbox.asked), 20)
        self.assertEqual(len(mailbox.asked), len(set(mailbox.asked)), "nessuna pagina chiesta due volte")

    async def test_about_sixty_real_seconds_in_all(self):
        mailbox = PagedMailbox("slow", total=40, valid_page=30, seconds_per_page=25.0)
        offers = await mailbox.run()
        self.assertEqual(offers, [])
        self.assertLessEqual(max(mailbox.asked), 5, "con 25 s a pagina si ferma dopo circa 60 s")
        self.assertGreaterEqual(max(mailbox.asked), 3)


if __name__ == "__main__":
    unittest.main()
