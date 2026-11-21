"""Care-protocol example. ``city init`` does not copy this file.

The scaffold brain is ``templates/agent/agent/agent.py``. This one is the full care
protocol (prescribe, offer, hold, commit, check-in, report), one inbound message per
step. The role is ``role`` in ``card.yaml``. Ledger writes are chat to ``city:ledger``;
citizens read the act word and ``key=value`` tokens (ADR-110).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from collections import OrderedDict, deque
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from secrets import token_hex
from time import monotonic

from city_sdk.city import LEDGER, CapError, City, Message, Need, OutOfScope, clinical, understood

ROLES = ("booking_centre", "gp", "hospital", "specialist_care", "family_counseling")
# The catalogue is read one page at a time until a valid batch turns up: at most 20 pages and about
# 60 real seconds per need (a valid slot on page 9 was never read when the cap was 8).
_MAX_PAGE = 20
_PAGING_SECONDS = 60.0
# One real minute is one agenda hour and a citizen answers after 3-27 minutes (console 21/11): a slot a few
# hours ahead is already past when it decides (`reason=past`, Ledger `EXPIRED`). Slots at least _LEAD ahead
# in agenda time come first, then the ones at least _MIN_LEAD ahead; nearer ones are never offered.
_LEAD = timedelta(hours=30)
# Simulation of the 21/11 journeys (tools/sim_percorsi.py): 10 hours is the best minimum (19/21 booked
# with a 4-minute CUP latency, 14/21 with 4 hours); U keeps 4 (same agenda day).
_MIN_LEAD = timedelta(hours=10)
_MIN_LEAD_U = timedelta(hours=4)
_CONFIRM_MARGIN = timedelta(hours=1)  # at confirm: enough for hold and commit


def _min_lead(priority: str | None) -> timedelta:
    return _MIN_LEAD_U if priority == "U" else _MIN_LEAD
# Doctor key (the last segment of doctor_id) -> languages, gender, days. ``*`` is the ASST's
# rare language. The Ledger's slot line names the doctor; it does not repeat this table.
_OWN_RARE_LANGUAGE = "ti"
_DOCTORS: dict[str, tuple[frozenset[str], str, frozenset[str]]] = {
    "h1": (frozenset({"it", "en"}), "f", frozenset({"mon", "tue", "wed"})),
    "h2": (frozenset({"it"}), "m", frozenset({"wed", "thu", "fri"})),
    "h3": (frozenset({"it", "*"}), "m", frozenset({"tue", "thu"})),
    "s1": (frozenset({"it", "en"}), "m", frozenset({"mon", "wed", "fri"})),
    "s2": (frozenset({"it"}), "f", frozenset({"tue", "thu"})),
    "c1": (frozenset({"it", "en"}), "f", frozenset({"mon", "tue", "wed", "thu", "fri"})),
}
_PROTOCOLS: dict[str, tuple[str, str]] = {
    "SYM-BACK": ("VIS-FIS", "B"),
    "SYM-KNEE": ("VIS-FIS", "D"),
    "SYM-PALPITATIONS": ("VIS-CARD", "B"),
    "SYM-FOLLOWUP": ("VIS-CARD", "P"),
}
_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("SYM-BACK", ("mal di schiena", "back pain")),
    ("SYM-KNEE", ("ginocchio", "knee")),
    ("SYM-PALPITATIONS", ("cuore che batte", "heart racing")),
    ("SYM-FOLLOWUP", ("controllo del cuore", "routine heart check")),
)
_RED_FLAGS = (
    "perdita di forza alle gambe",
    "loss of strength in the legs",
    "dolore al petto",
    "chest pain",
)
_DEADLINE_DAYS = {"B": 2, "D": 5}


def _agenda_horizon(now: datetime, days: int) -> datetime:
    """``now`` plus ``days`` days of AGENDA. Saturday and Sunday do not exist in the agenda: after
    Friday it goes on from Monday (kit, ADR-124). B on a Thursday ends on Monday, not on Saturday:
    calendar days dropped every Monday slot and left Thursday and Friday cases with nothing."""

    at = now
    left = days
    while left > 0:
        at += timedelta(days=1)
        if at.weekday() < 5:
            left -= 1
    return at
_RX = re.compile(r"^prescription_number-[A-Z0-9-]{4,40}$")
_LOG = logging.getLogger("care")
_LOGGED_REPLIES: set[str] = set()
# The Relay accepts a ledger reply and then the agent rejects the push, so the reply sits in
# the case history and never opens a turn. Wait briefly and read it back from history.
_PULL_TRIES = 24
_PULL_PAUSE = 0.25
# Needs whose sent offers this process remembers; the oldest is forgotten first.
_SENT_NEEDS = 4096
_CUP_MAX_TEXT = 2000
_AGENDA_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_AGENDA_DAYS = frozenset(_AGENDA_WEEKDAYS[:5])
_CUP_SERVICES = {
    "VIS-FIS": "hospital.physiatry",
    "VIS-CARD": "specialist_care.cardiology",
    "CTRL-CARD": "specialist_care.cardiology",
}
_CUP_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}")
# Console 21/11 04:43-05:09: 22 searches asked 25 partners each (550 messages and about 500 replies, each
# one a turn of ours); seven partners sent the 45 offers and one offer reached a citizen. Ask at most six,
# the ones that offer first.
_CUP_MAX_PARTNERS = 6
_CUP_PRODUCTIVE = {
    "hospital.physiatry": (
        "agent:r8njm9a6c7pv", "agent:darwa6412gz0", "agent:x0vr9rbwpesr", "agent:m6py14a1ej77", "agent:gxq3vzgt3h5t",
    ),
    "specialist_care.cardiology": ("agent:h6krzxx6es83", "agent:hnpe58epeyh1"),
}
_PARTNER_GOOD: dict[str, dict[str, None]] = {}  # service -> partners whose offer fitted a citizen here
# Level 4: facilities other teams published on the event Discord (21/11, 00:00-00:40), with the
# rare language of their h3. city.find alone did not bring partner offers (journeys 153, 165, 166:
# answer set not empty, no partner slot). Only search criteria travel before the cross_asst consent.
_CUP_RING = (
    # (h3 language, hospital.physiatry, specialist_care.cardiology)
    ("ka", "agent:h6r1v45esk77", "agent:hnpe58epeyh1"),  # Giambellino
    ("ur", "agent:gpr1zqe343gb", "agent:zand0f57ec1j"),  # Nord
    ("ja", "agent:nanpr5mgm2py", "agent:pky3vqyqbepa"),  # Lambrate
    ("si", "agent:xtj1dk9x3qej", "agent:q18es2d82f8r"),  # Greco
    ("fr", "agent:x0vr9rbwpesr", "agent:h8425ac7btd8"),  # Corvetto
    ("", "agent:tmt0bcv0st1f", "agent:n9bf9y6670hp"),    # Lorenteggio
    # Added from the MACH-1.2 ring list (01:23): the six above all replied no_availability.
    ("ro", "agent:s1twcdzg3296", "agent:f2s88vwd3jnf"),  # Precotto / Toros
    ("", "agent:gxq3vzgt3h5t", "agent:tty8erdj6t41"),    # Bovisa
    ("tl", "", "agent:etpwrfmfa8hm"),                    # Isola (hospital id not published)
)
_CUP_RING_COLUMN = {"hospital.physiatry": 1, "specialist_care.cardiology": 2}


def _cup_partner_candidates(found: list[str], service: str, local: set[str], language: str) -> list[str]:
    """Known ring facilities first (the one whose h3 speaks the citizen's language at the top),
    then whatever city.find returned; never our own facilities."""
    column = _CUP_RING_COLUMN.get(service)
    ring = [] if column is None else sorted(_CUP_RING, key=lambda row: row[0] != language)
    known = [row[column] for row in ring if row[column]]
    speaker = [row[column] for row in ring if row[column] and row[0] and row[0] == language]
    learned = list(_PARTNER_GOOD.get(service, {}))
    productive = [agent for agent in _CUP_PRODUCTIVE.get(service, ()) if agent in found]  # still in the Index
    ordered = dict.fromkeys([*speaker, *learned, *productive, *found, *known])
    return [agent for agent in ordered if agent not in local and _CUP_TOKEN.fullmatch(agent)][:_CUP_MAX_PARTNERS]

_CUP_PARTNER_REPLY_SECONDS = 15
_CUP_CONFIRM_WAIT = 180  # real seconds without receipt or cancel from the facility


def role_of() -> str:
    """The role this process serves, from ``CITY_ROLE`` or the card next to the brain."""

    forced = os.environ.get("CITY_ROLE", "").strip()
    if forced in ROLES:
        return forced
    path = os.environ.get("CITY_CARD", "")
    if not path:
        return ""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""
    return _card_role(text)


async def main(need: Need, city: City) -> None:
    message = city.inbound
    if message is None:
        return
    text = message.text or need.summary
    if clinical(text):
        raise OutOfScope()
    role = role_of()
    if role == "booking_centre":
        if not message.need_id:
            return
        async with _case_lock(message.need_id):
            chat = await _load_case_history(city, message.need_id)
            if chat is not None:
                await handle(role, city, message, chat)
        return
    # With no CUP role, handle only serves the stateless address inquiry.
    await handle(role, city, message, [])


def _asks_address(message: Message) -> bool:
    """True when this turn is a ``data.request`` that names the field ``address``."""

    text = message.text
    if text:
        named = False
        asked = False
        for token in text.split():
            bare = token.strip(".,;:!?()\"'")
            if bare == "data.request":
                named = True
            key, eq, value = bare.partition("=")
            if eq and key == "fields":
                names = {part.strip() for part in value.split(",") if part.strip()}
                asked = asked or "address" in names
        return named and asked
    if message.type != "data.request":
        return False
    raw = message.body.get("fields")
    if isinstance(raw, list):
        return "address" in raw
    if isinstance(raw, str):
        return "address" in {part.strip() for part in raw.replace(",", " ").split() if part.strip()}
    return False


def _own_street(city: City) -> str:
    """This agent's door: the city value, else the street shipped beside the brain."""

    street = getattr(city, "address", "")
    if isinstance(street, str) and street.strip():
        return street.strip()
    env = os.environ.get("CITY_ADDRESS", "").strip()
    if env:
        return env
    path = Path(__file__).with_name("door.txt")
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


async def handle(role: str, city: City, message: Message, chat: list[Message]) -> None:
    street = _own_street(city)
    if street and _asks_address(message):
        await city.say(message.sender, f"address={street}")
        return
    # This file serves only its own role: the other roles' code was removed to keep the
    # brain small for the city's deploy scan (see team/DECISIONS.md).
    if role == "booking_centre":
        await _booking_centre(city, message, chat)


# --- shared ------------------------------------------------------------------------------------


def _card_role(text: str) -> str:
    role = ""
    types: list[str] = []
    in_types = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line[0] in " \t":
            if in_types:
                item = line.strip().removeprefix("-").strip().strip("'\"")
                if item:
                    types.append(item)
            continue
        in_types = False
        key, _, value = line.partition(":")
        value = value.strip().strip("'\"")
        if key.strip() == "role":
            role = value
        elif (
            key.strip() in {"capabilities", "service_types"}
            and value.startswith("[")
            and value.endswith("]")
        ):
            types = [part.strip().strip("'\"") for part in value[1:-1].split(",") if part.strip()]
        elif key.strip() in {"capabilities", "service_types"}:
            in_types = True
    if role in ROLES:
        return role
    for family in ("specialist_care", "family_counseling", "hospital", "booking_centre", "gp"):
        if any(item == family or item.startswith(family + ".") for item in types):
            return family
    return "hospital" if role == "facility" else ""


def words(text: str) -> set[str]:
    return {token.strip(".,;:!?()\"'").lower() for token in text.split() if token.strip()}


def first_word(text: str) -> str:
    parts = text.split()
    return parts[0].strip(".,;:!?()\"'").lower() if parts else ""


def fields_of(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for token in text.replace(",", " ").split():
        key, eq, value = token.partition("=")
        if not eq or not key or not value:
            continue
        value = value.strip(".,;:!?")
        if key not in found and value:
            found[key] = value
    return found


def _when(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        # MACH-1.1 partners write ISO dates without an offset; the Ledger and the world use UTC.
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _utc(at: datetime) -> str:
    return at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _citizen(chat: list[Message]) -> str | None:
    for row in chat:
        if row.sender.startswith("citizen:"):
            return row.sender
    for row in chat:
        fields = fields_of(row.text)
        for key in ("patient", "citizen"):
            party = fields.get(key, "")
            if party.startswith("citizen:"):
                return party
    return None


def _we(chat: list[Message], agent: str, token: str, *, to: str, word: str) -> bool:
    for row in chat:
        if row.sender != agent or row.recipient != to:
            continue
        if token in row.text.split() and word in words(row.text):
            return True
    return False


def _exact(chat: list[Message], agent: str, text: str) -> bool:
    return any(row.sender == agent and row.text.strip() == text for row in chat)


def _history_can_retry(error: CapError) -> bool:
    try:
        return 500 <= error.http_status() < 600
    except CapError:
        return False  # An unknown CAP code does not authorize a retry.


async def _load_case_history(city: City, need_id: str) -> list[Message] | None:
    """Load the authoritative case before processing an inbound message."""

    for attempt in range(2):
        try:
            return await city.history(need_id=need_id)
        except CapError as error:
            if attempt or not _history_can_retry(error):
                _LOG.warning("cup.history.failed need=%s code=%s", need_id, error.code)
                break
    return None


async def _until(
    city: City,
    need_id: str | None,
    chat: list[Message],
    ready: Callable[[list[Message]], bool],
    *,
    max_polls: int | None = None,
) -> list[Message] | None:
    """Re-read the case until ``ready`` or the short wait ends. The push may never arrive."""

    if not need_id:
        return None
    fresh = chat
    previous_failed = False
    polls = _PULL_TRIES if max_polls is None else min(max_polls, _PULL_TRIES)
    for attempt in range(polls):
        try:
            fresh = await city.history(need_id=need_id)
        except CapError as error:
            if previous_failed or not _history_can_retry(error):
                _LOG.warning("cup.history.failed need=%s code=%s", need_id, error.code)
                return None
            previous_failed = True
        else:
            previous_failed = False
            if ready(fresh):
                return fresh
        if attempt + 1 < polls:
            await asyncio.sleep(_PULL_PAUSE)
    return fresh


_AGENDA_RATE = 60  # agenda minutes per real minute (/v1/team/wave "rate")


def _agenda_add(start: datetime, delta: timedelta) -> datetime:
    """``start`` plus ``delta`` of agenda time. The agenda has no weekend: Saturday and Sunday are
    skipped, so Friday 23:00 plus two hours is Monday 01:00."""
    out = start
    while delta > timedelta(0):
        midnight = (out + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        step = min(delta, midnight - out)
        out, delta = out + step, delta - step
        if out.weekday() >= 5:
            out += timedelta(days=7 - out.weekday())
    return out


def _agenda_now(chat: list[Message], real_now: datetime | None = None) -> datetime | None:
    """The agenda clock now: the Ledger's last agenda_now plus the real time since that reply.

    The agenda runs 60x: a need resumed a few minutes later otherwise works hours in the past
    (log cup.partners at 00:52 used 09:36 while the agenda was past 16:00)."""
    found: tuple[datetime, datetime | None] | None = None
    for row in chat:
        if row.sender == LEDGER and first_word(row.text) == "agenda":
            at = _when(fields_of(row.text).get("agenda_now", ""))
            if at is not None:
                found = (at, _when(row.sent_at or ""))
    if found is None:
        return None
    at, read = found
    if read is None:
        return at
    elapsed = (real_now or datetime.now(timezone.utc)) - read
    return _agenda_add(at, max(elapsed, timedelta(0)) * _AGENDA_RATE)


def _has_agenda(chat: list[Message]) -> bool:
    agenda = _ledger(chat, "agenda")
    return _when("" if agenda is None else agenda.get("agenda_now", "")) is not None


def _doctor_spec(doctor_id: str) -> tuple[frozenset[str], str, frozenset[str]] | None:
    return _DOCTORS.get(doctor_id) or _DOCTORS.get(doctor_id.rsplit("-", 1)[-1])


def _unknown_doctor_ok(lang: str, gender: str | None) -> bool:
    # The live world may use doctor ids that are not in the hand-written table (the kit
    # example uses D-3). Keep such a slot only for Italian with no gender preference: the language
    # and gender of an unknown doctor cannot be checked.
    return lang in {"it", ""} and not gender


def _speaks(doctor_id: str, lang: str) -> bool:
    spec = _doctor_spec(doctor_id)
    if spec is None:
        return _unknown_doctor_ok(lang, None)
    langs = spec[0]
    if lang in langs:
        return True
    # "*" is the rare language of the doctor's own ASST. fitting() only reads our own world
    # slice, so for our h3 that is Tigrinya (registry: asst-bicocca-h3 speaks it/ti). Any other
    # rare language was offered to the wrong citizen (142: lang=hi got our h3).
    return "*" in langs and lang == _OWN_RARE_LANGUAGE


def _ahead(now: datetime, at: datetime) -> timedelta:
    """Agenda time from ``now`` to ``at``: Saturday and Sunday do not exist in the agenda, so the
    days between do not count (Friday 17:00 to Monday 10:30 is 17 hours and a half)."""
    at = at.astimezone(now.tzinfo)
    gap, day = at - now, now.date()
    for _ in range(max((at.date() - day).days - 1, 0)):
        day += timedelta(days=1)
        if day.weekday() >= 5:
            gap -= timedelta(days=1)
    return gap


def _lead(priority: str | None) -> timedelta:
    """B and U windows are short: the soonest slot past the minimum wins. Elsewhere 30 hours first."""
    return _min_lead(priority) if priority in ("B", "U") else _LEAD


# Console 21/11: the citizen writes to the CUP 19-20 real minutes (agenda hours) after the GP's
# prescription, and its B/D deadline counts from the prescription (187: B prescribed Tue 01/12 ~05:00,
# 03/12 10:30 refused for deadline, 02/12 10:30 confirmed). Our window started when WE answered.
_TO_CUP = timedelta(hours=21)  # 19.5-20.6 minutes in 17 journeys: one hour of margin


def _true_deadline(chat: list[Message], citizen: str, priority: str | None) -> datetime | None:
    if priority not in _DEADLINE_DAYS:
        return None
    first = next((row for row in chat if row.sender == citizen and row.sent_at), None)
    start = _agenda_now(chat, _when(first.sent_at)) if first is not None else None
    return None if start is None else _agenda_horizon(start - _TO_CUP, _DEADLINE_DAYS[priority])


def fitting(
    lines: list[str],
    *,
    now: datetime,
    priority: str | None,
    lang: str,
    gender: str | None = None,
    facility: str | None = None,
    procedure: str | None = None,
    days: set[str] | None = None,
    relax_window: bool = False,
    until: datetime | None = None,
) -> list[dict[str, str]]:
    """Available slots that satisfy the citizen's preferences and the prescribed priority."""

    if relax_window or priority == "P":
        horizon: datetime | None = None
    elif priority == "U":
        horizon = now.replace(hour=23, minute=59, second=59, microsecond=0)
    else:
        horizon = _agenda_horizon(now, _DEADLINE_DAYS.get(priority or "", 14))
    if until is not None and horizon is not None and not relax_window:
        horizon = min(horizon, until)
    earliest = now + _min_lead(priority)
    lead = _lead(priority)
    chosen: list[tuple[datetime, dict[str, str]]] = []
    for line in lines:
        slot = fields_of(line)
        slot_id = slot.get("slot_id")
        doctor = slot.get("doctor_id")
        timestamp = slot.get("agenda_date") or slot.get("at", "")
        at = _when(timestamp)
        if not slot_id or not doctor or at is None:
            continue
        day = _AGENDA_WEEKDAYS[at.weekday()]
        stated_day = slot.get("agenda_day") or slot.get("day") or day
        if day not in _AGENDA_DAYS or stated_day.lower() != day or (days and day not in days):
            continue
        slot["at"], slot["day"] = timestamp, day
        if procedure and slot.get("procedure") not in (None, procedure):
            continue
        if facility and slot.get("facility") != facility:
            continue
        free = slot.get("free", slot.get("capacity", "1"))
        if not free.isdecimal() or int(free) <= 0:
            continue
        reserve = slot.get("urgent_reserve", "").lower() == "true"
        if reserve and priority != "U":
            continue
        if not earliest < at or (horizon is not None and at >= horizon):
            continue
        if not _speaks(doctor, lang):
            continue
        spec = _doctor_spec(doctor)
        if spec is None:
            if _unknown_doctor_ok(lang, gender):
                chosen.append((at, slot))
            continue
        if day not in spec[2]:
            continue
        if gender and spec[1] != gender:
            continue
        chosen.append((at, slot))
    chosen.sort(key=lambda item: (_ahead(now, item[0]) < lead, item[0], item[1].get("slot_id", "")))
    return [slot for _, slot in chosen]


# --- medico di base ----------------------------------------------------------------------------


# --- centro prenotazioni and consultorio -------------------------------------------------------


def _ledger(chat: list[Message], head: str) -> dict[str, str] | None:
    found: dict[str, str] | None = None
    for row in chat:
        if row.sender == LEDGER and first_word(row.text) == head:
            found = fields_of(row.text)
    return found


def _latest_slots(chat: list[Message]) -> str | None:
    found: str | None = None
    for row in chat:
        if row.sender == LEDGER and first_word(row.text) == "slots":
            found = row.text
    return found


def _page(text: str) -> tuple[int, int]:
    raw = fields_of(text.splitlines()[0] if text else "").get("page", "")
    left, _, right = raw.partition("/")
    if left.isdigit() and right.isdigit():
        return int(left), int(right)
    return 1, 1


# Console 21/11 05:00-05:15: the Ledger answered agenda, prescription and world 7-9 real minutes after
# the request (CUP, GP and consultorio alike) and the reply opened our next turn 6-7 minutes later: each
# read costs agenda hours. The agenda clock and the slot pages are the same for every need of a wave, so
# a reading made for one need serves the others for a few minutes.
_SHARED_SECONDS = 300
_SHARED: dict[tuple[str, str], tuple[Message, datetime]] = {}
_PAGE_BURST = 6  # missing catalogue pages asked in one turn, not one page per Ledger round trip


def _wave(party: str) -> str:
    return party.removeprefix("citizen:").split("-", 1)[0]


def _shared_key(row: Message) -> tuple[str, str] | None:
    """(wave, "agenda") or (wave, "<procedure> p<page>") for a Ledger agenda or slot page."""
    lines = row.text.splitlines()
    top = fields_of(lines[0]) if lines and row.sender == LEDGER else {}
    wave, head = top.get("wave_id", ""), first_word(row.text)
    if not wave:
        return None
    if head == "agenda" and _when(top.get("agenda_now", "")) is not None and top.get("paused") != "true":
        return wave, "agenda"
    procedures = {fields_of(line).get("procedure") for line in lines[1:]} - {None}
    if head == "slots" and len(procedures) == 1:
        return wave, f"{procedures.pop()} p{_page(row.text)[0]}"
    return None


def _shared_reads(chat: list[Message], citizen: str, procedure: str | None) -> list[Message]:
    """Remember this need's agenda and slot pages; put before the chat the ones other needs of the same
    wave read in the last few minutes and this need lacks (its own readings come later and win)."""
    wave, now, have = _wave(citizen), datetime.now(timezone.utc), set()
    for row in chat:
        key = _shared_key(row)
        if key is None or key[0] != wave:
            continue
        have.add(key)
        read = _when(row.sent_at or "") or now
        if key not in _SHARED or _SHARED[key][1] <= read:
            _SHARED[key] = (row, read)
    shared = [
        row for (owner, kind), (row, read) in _SHARED.items()
        if owner == wave and (owner, kind) not in have and now - read <= timedelta(seconds=_SHARED_SECONDS)
        and (kind == "agenda" or (procedure is not None and kind.startswith(procedure + " p")))
    ]
    return [*shared, *chat] if shared else chat


_CUP_HINT = {"hospital.physiatry": "VIS-FIS", "specialist_care.cardiology": "VIS-CARD"}


def _procedure_hint(chat: list[Message], citizen: str) -> str | None:
    """The procedure the citizen's service_type points to, to read the catalogue with the prescription."""
    for row in reversed(chat):
        if row.sender == citizen and (hint := _CUP_HINT.get(fields_of(row.text).get("service_type", ""))):
            return hint
    return None


def _asked(chat: list[Message], agent: str, procedure: str, page: int) -> bool:
    token = f"page={page}"
    proc = f"procedure={procedure}"
    for row in chat:
        if row.sender == agent and token in row.text.split() and proc in row.text.split():
            return True
    return False


def _offered(chat: list[Message], agent: str) -> set[str]:
    found: set[str] = set()
    for row in chat:
        if row.sender != agent:
            continue
        for offer in _offer_blocks(row.text):
            if slot := offer.get("slot_id"):
                found.add(slot)
    return found


def _withdrawn(chat: list[Message], agent: str) -> set[str]:
    """Slots we cancelled. The citizen drops the rest, so those are offered again."""

    by_offer: dict[str, str] = {}
    confirmed_slots: dict[str, str] = {}
    dropped: set[str] = set()
    for row in chat:
        if row.sender != agent:
            continue
        for offer in _offer_blocks(row.text):
            offer_id = offer["offer_id"]
            if slot := offer.get("slot_id"):
                by_offer[offer_id] = slot
        act = first_word(row.text)
        fields = fields_of(row.text)
        number = fields.get("prescription_number", "")
        if act == "confirm" and number and (slot := fields.get("slot_id")):
            confirmed_slots[number] = slot
        slot = None
        if act == "cancel":
            slot = fields.get("slot_id") if fields.get("booking_id") else by_offer.get(fields.get("offer_id", ""))
        elif act == "data.request" and fields.get("purpose") == "prescription_renewal":
            slot = confirmed_slots.get(number)
        if slot:
            dropped.add(slot)
    return dropped


def _cup_number(chat: list[Message], citizen: str, expired: set[str]) -> str | None:
    current = None
    seen_expired = set()
    for row in chat:
        if row.sender != citizen:
            continue
        act, fields = _cup_input(row)
        if act in {"confirm", "consent", "cancel", "booking.receipt", "refused"}:
            continue
        if act == "data.response" and fields.get("purpose") not in (None, "prescription_renewal"):
            continue
        number = fields.get("prescription_number", "")
        if not _CUP_TOKEN.fullmatch(number):
            continue
        if number not in expired:
            current = number
        elif number not in seen_expired:
            # An expired reference superseded earlier intake. Later replays cannot replace a renewal.
            current = None
            seen_expired.add(number)
    return current


def _cup_prescription(chat: list[Message], number: str | None, citizen: str) -> dict[str, str] | None:
    for row in reversed(chat):
        if row.sender != LEDGER:
            continue
        act, fields = _cup_input(row)
        if fields.get("prescription_number") != number or not number:
            continue
        if any(fields.get(key, citizen) != citizen for key in ("citizen", "patient")):
            continue
        if act == "prescription":
            return fields
        if act == "refused" and fields.get("code") == "PRESCRIPTION_EXPIRED":
            return {**fields, "state": "expired"}
    return None


def _lang(chat: list[Message], citizen: str) -> str:
    for row in reversed(chat):
        if row.sender == citizen:
            lang = row.body.get("lang") or fields_of(row.text).get("lang")
            if isinstance(lang, str) and _CUP_TOKEN.fullmatch(lang):
                return lang.lower()
    return "it"


def _refused(chat: list[Message], citizen: str, reason: str) -> list[dict[str, str]]:
    """Our offers the citizen turned down with ``cancel offer_id=... reason=<reason>``."""
    shown = {o["offer_id"]: o for row in chat if row.sender != citizen for o in _offer_blocks(row.text)}
    found = []
    for row in chat:
        if row.sender == citizen:
            act, fields = _cup_input(row)
            if act == "cancel" and fields.get("reason") == reason and fields.get("offer_id") in shown:
                found.append(shown[fields["offer_id"]])
    return found


def _gender(chat: list[Message], citizen: str) -> str | None:
    """The doctor's gender the citizen asked for; else the opposite of the one it refused with
    ``reason=gender`` (the citizens never state it: console 21/11, journeys 255, 249, 225)."""
    for row in reversed(chat):
        if row.sender != citizen:
            continue
        fields = fields_of(row.text) if row.type == "chat" else row.body
        raw = fields.get("gender_preference") or fields.get("gender")
        if isinstance(raw, str) and raw.lower() in {"m", "f"}:
            return raw.lower()
    refused = set()
    for offer in _refused(chat, citizen, "gender"):
        spec = _doctor_spec(offer.get("doctor_id", ""))
        refused.add(spec[1] if spec else offer.get("doctor_gender", ""))
    return {"m": "f", "f": "m"}.get(next(iter(refused)) if len(refused) == 1 else "")


_IT_DAYS = {
    "lunedi": "mon", "martedi": "tue", "mercoledi": "wed", "giovedi": "thu", "venerdi": "fri",
    "monday": "mon", "tuesday": "tue", "wednesday": "wed", "thursday": "thu", "friday": "fri",
    # "posso solo lun/mer/ven" (288)
    "lun": "mon", "mar": "tue", "mer": "wed", "gio": "thu", "ven": "fri",
    "mon": "mon", "tue": "tue", "wed": "wed", "thu": "thu", "fri": "fri",
}


def _cup_days(chat: list[Message], citizen: str) -> set[str]:
    """Days the citizen can come: days= first, else the weekdays named in its text ("solo lunedì o
    mercoledì"), minus the weekdays of offers refused with ``reason=day``. Empty: no restriction."""
    stated = _stated_days(chat, citizen) or _named_days(chat, citizen)
    refused = {offer.get("agenda_day", "") for offer in _refused(chat, citizen, "day")} & _AGENDA_DAYS
    left = (stated or set(_AGENDA_DAYS)) - refused
    return left if refused and left else stated


def _named_days(chat: list[Message], citizen: str) -> set[str]:
    for row in reversed(chat):
        if row.sender == citizen and "cancel" not in words(row.text):
            found = {_IT_DAYS[w] for w in re.findall(r"[a-z]+", row.text.lower().replace("ì", "i")) if w in _IT_DAYS}
            if found:
                return found
    return set()


def _stated_days(chat: list[Message], citizen: str) -> set[str]:
    for row in reversed(chat):
        if row.sender != citizen:
            continue
        value = row.body.get("days")
        if isinstance(value, (tuple, list)):
            days = {day.lower() for day in value if isinstance(day, str)}
        else:
            match = re.search(r"(?:^|\s)days=(\[[^\]]*\]|[^\s]+)", row.text)
            raw = value if isinstance(value, str) else (match[1] if match else "")
            days = set(re.split(r"[\s,;/|\[\]]+", raw.lower()))
        if recognized := days & _AGENDA_DAYS:
            return recognized
    return set()


def _offer_line(
    slot: dict[str, str], number: str | None, priority: str | None, *, offer_id: str | None = None
) -> str:
    parts = [
        "offer",
        f"offer_id={offer_id or 'of-' + slot['slot_id']}",
        f"slot_id={slot['slot_id']}",
        f"doctor_id={slot['doctor_id']}",
        f"facility={slot['facility']}",
        f"procedure={slot['procedure']}",
        f"agenda_date={slot['at']}",
        f"agenda_day={slot['day']}",
        f"expiry={slot.get('expiry', slot['at'])}",
    ]
    if priority:
        parts.append(f"priority={priority}")
    if number:
        parts.append(f"prescription_number={number}")
    return " ".join(parts)


def _offer_blocks(text: str) -> list[dict[str, str]]:
    offers = []
    for line in text.splitlines():
        if first_word(line) == "offer":
            fields = fields_of(line)
            if fields.get("offer_id"):
                offers.append(fields)
    return offers


class _Gate:
    """One need's lock and how many turns hold it or wait for it."""

    __slots__ = ("lock", "turns")

    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.turns = 0


class _Sent:
    """Offers this process sent for one need, which the case history may not show yet.

    ``offers`` holds every slot id (and waiting-list offer id) sent. A cancel makes the
    citizen drop all offers, so ``again`` holds only what was re-sent for ``trigger``.
    """

    __slots__ = (
        "offers", "trigger", "again", "outbox", "uncertain_confirmation", "partner_search_started", "stale_reads",
        "partner_search_retried", "paging_started", "confirm_sent_at", "confirm_resent",
    )

    def __init__(self) -> None:
        self.offers: set[str] = set()
        self.trigger = ""
        self.again: set[str] = set()
        self.outbox: deque[tuple[Message, str]] = deque(maxlen=16)
        self.uncertain_confirmation = False
        self.partner_search_started: float | None = None
        self.partner_search_retried = False
        # Ledger agenda/slots answers read before a P1 renewal: stale once the renewal is asked.
        self.stale_reads: set[str] = set()
        self.paging_started: float | None = None
        # The confirm to the facility: when it left and whether it was sent again (3590002).
        self.confirm_sent_at: float | None = None
        self.confirm_resent = False


# Turns of the same need may overlap. Keep state-changing CUP turns serial and
# read history after acquiring the lock, so they see preceding decisions.
# An entry lives only while a turn holds or waits on its lock.
_GATES: dict[str, _Gate] = {}
_SENT: OrderedDict[str, _Sent] = OrderedDict()


def _sent(key: str) -> _Sent:
    entry = _SENT.get(key)
    if entry is None:
        entry = _SENT[key] = _Sent()
        while len(_SENT) > _SENT_NEEDS:
            _SENT.popitem(last=False)
    else:
        _SENT.move_to_end(key)
    return entry


@asynccontextmanager
async def _case_lock(key: str) -> AsyncIterator[None]:
    gate = _GATES.get(key)
    if gate is None:
        gate = _GATES[key] = _Gate()
    gate.turns += 1
    try:
        async with gate.lock:
            yield
    finally:
        gate.turns -= 1
        if gate.turns == 0 and _GATES.get(key) is gate:
            del _GATES[key]


@dataclass
class _CupCase:
    offers: dict[str, dict[str, str]] = field(default_factory=dict)
    declined_slots: set[str] = field(default_factory=set)
    cross_consent_request: Message | None = None
    cross_asst_declined: bool = False
    confirmation: Message | None = None
    cancellation: Message | None = None
    renewal_request: Message | None = None
    expired_prescriptions: set[str] = field(default_factory=set)
    receipt: Message | None = None


def _cup_case(chat: list[Message], agent: str, citizen: str) -> _CupCase:
    state = _CupCase()
    for row in chat:
        if row.sender == citizen:
            act, fields = _cup_input(row)
            offer_id = fields.get("offer_id", "")
            declined = state.offers.pop(offer_id, None) if act == "cancel" else None
            if declined is not None:
                if slot := declined.get("slot_id"):
                    state.declined_slots.add(slot)
                ask = state.cross_consent_request
                if ask is not None and fields_of(ask.text).get("offer_id") == offer_id:
                    state.cross_consent_request = None
                if not state.offers:
                    state.cancellation = row
            elif state.cross_consent_request is not None and state.confirmation is None:
                _, refused = _cup_cross_reply(row, state.cross_consent_request, act, fields)
                state.cross_asst_declined |= refused
            continue
        if row.sender != agent:
            continue
        act = first_word(row.text)
        fields = fields_of(row.text)
        if row.recipient == citizen:
            if act == "offer":
                offers = _offer_blocks(row.text)
                # The reference used a separate message and of-<slot_id> for each offer.
                legacy = len(offers) == 1 and offers[0]["offer_id"] == "of-" + offers[0].get("slot_id", "")
                if not legacy:
                    state.offers.clear()
                    state.cross_consent_request = None
                state.offers.update({offer["offer_id"]: offer for offer in offers})
                state.cancellation = None
                state.renewal_request = None
            elif act == "cancel":
                state.offers.clear()
                state.cross_consent_request = None
                state.confirmation = None
                state.cancellation = row
                state.receipt = None
                if fields.get("reason") == "consent_declined":
                    state.cross_asst_declined = True
            elif act == "data.request" and fields.get("purpose") == "prescription_renewal":
                if number := fields.get("prescription_number"):
                    state.expired_prescriptions.add(number)
                    state.offers.clear()
                    state.cross_consent_request = None
                    state.confirmation = None
                    state.cancellation = None
                    state.renewal_request = row
            elif act == "consent" and fields.get("purpose") == "cross_asst":
                if fields.get("offer_id") in state.offers:
                    state.cross_consent_request = row
            elif act == "booking.receipt" and fields.get("booking_id") and fields.get("ledger_ref"):
                state.receipt = row
        elif act == "confirm" and fields.get("citizen") == citizen and row.recipient.startswith("agent:"):
            state.confirmation = row
    return state


def _cup_input(message: Message, *, first_line: bool = False) -> tuple[str, dict[str, str]]:
    if message.type != "chat":
        return message.type, {
            key: value for key, value in message.body.items()
            if isinstance(value, str) and value and not any(char.isspace() for char in value)
        }
    text = message.text.partition("\n")[0] if first_line else message.text
    acts = words(text) & {"confirm", "booking.receipt", "cancel", "consent", "data.response", "refused", "hold_refused"}
    if len(acts) > 1:
        return "", {}
    act = next(iter(acts), first_word(text))
    fields: dict[str, str] = {}
    for token in text.replace(",", " ").split():
        key, equals, value = token.partition("=")
        if not equals:
            continue
        if not key or not value or key in fields:
            return act, {}
        fields[key] = value.strip(".,;:!?")
    return act, fields


async def _cup_post(city: City, inbound: Message, cache: _Sent, to: str, text: str) -> None:
    msg_id = await city.say(to, text)
    sent = Message(
        type="chat", sender=city.agent_id, msg_id=msg_id, recipient=to,
        need_id=inbound.need_id, conversation_id=inbound.conversation_id, body={"text": text},
    )
    cache.outbox.append((sent, inbound.msg_id))


async def _cup_send(city: City, inbound: Message, cache: _Sent, to: str, text: str) -> bool:
    try:
        await _cup_post(city, inbound, cache, to, text)
    except CapError:
        return False
    return True


def _cup_history(chat: list[Message], cache: _Sent, agent: str, need_id: str) -> list[Message]:
    # A Ledger or facility response may use another conversation within the same need.
    case = [row for row in chat if row.need_id == need_id and agent in (row.sender, row.recipient)]
    positions = {row.msg_id: index for index, row in enumerate(case, 1)}
    missing: dict[int, list[Message]] = {}
    after = 0
    # Keep the Relay's oldest-first history. Insert missing sends after their trigger
    # and the preceding send, preserving send order when both have the same position.
    for row, trigger in cache.outbox:
        if row.msg_id in positions:
            after = positions[row.msg_id]
        else:
            after = max(after, positions.get(trigger, 0))
            missing.setdefault(after, []).append(row)
    if not missing:
        return case
    merged = list(missing.get(0, ()))
    for index, row in enumerate(case, 1):
        merged.append(row)
        merged.extend(missing.get(index, ()))
    return merged


def _cup_cancelled_booking(message: Message, receipt: Message, confirmation: Message) -> tuple[str, str] | None:
    # A facility may attach new offers below the cancellation, with different slot and offer IDs.
    if message.type == "chat":
        act, fields = _cup_input(message, first_line=True)
        if act != first_word(message.text):
            return None
    else:
        act, fields = message.type, message.body
    city_fault = message.sender.startswith("city:") and act in {"fault.cancel", "booking.cancelled"}
    facility_cancel = message.sender == confirmation.recipient and act == "cancel"
    if not (city_fault or facility_cancel):
        return None
    if not fields.get("booking_id") and not (city_fault and fields.get("slot_id")):
        return None  # A facility's pre-commit refusals carry an offer or a slot, but no booking ID.
    booked = fields_of(receipt.text)
    confirmed = fields_of(confirmation.text)
    if not (slot := confirmed.get("slot_id")):
        return None
    expected = {
        "booking_id": booked["booking_id"], "ledger_ref": booked["ledger_ref"],
        "slot_id": slot, "facility": confirmation.recipient, "citizen": receipt.recipient,
        "offer_id": confirmed.get("offer_id"), "cup_offer_id": confirmed.get("cup_offer_id"),
        "request_id": confirmed.get("request_id"), "prescription_number": confirmed.get("prescription_number"),
    }
    if any(key in fields and fields[key] != value for key, value in expected.items()):
        return None
    return booked["booking_id"], slot


async def _booking_centre(city: City, message: Message, chat: list[Message]) -> None:
    if message.sender == city.agent_id or not message.need_id:
        return
    key = message.need_id
    cache = _sent(key)
    if not any(row.msg_id == message.msg_id for row in chat):
        chat = [*chat, message]
    chat = _cup_history(chat, cache, city.agent_id, key)
    citizen = next((row.sender for row in chat if row.sender.startswith("citizen:")), None)
    if citizen is None:
        return
    chat = _shared_reads(chat, citizen, None)  # the agenda clock, for the confirm check too

    state = _cup_case(chat, city.agent_id, citizen)
    if state.receipt is not None:
        if state.confirmation and (cancelled := _cup_cancelled_booking(message, state.receipt, state.confirmation)):
            booking_id, slot = cancelled
            await _cup_cancel(
                city, message, chat, cache, citizen,
                f"cancel booking_id={booking_id} slot_id={slot} reason=facility_cancelled "
                "La struttura ha annullato la visita. Cerco subito un altro orario per lei.",
            )
        return
    act, fields = _cup_input(message)
    pending = state.confirmation
    number = _cup_number(chat, citizen, state.expired_prescriptions)
    if pending is not None:
        number = fields_of(pending.text).get("prescription_number")
    if number and (pending is None or message.sender == LEDGER):
        reply = _cup_prescription(chat if pending is None else [message], number, citizen)
        if reply is not None and reply.get("state") == "expired":
            await _cup_request_renewal(city, message, chat, cache, citizen, number)
            return

    if pending is not None and message.sender == citizen and cache.confirm_sent_at is not None:
        # 3590002: the citizen confirmed and the facility never answered (no receipt, no cancel)
        # for 32 minutes. A citizen turn after _CUP_CONFIRM_WAIT sends the same confirm once
        # (facilities treat a repeated confirm as the same booking); a second silence releases the
        # citizen and the search starts again.
        if monotonic() - cache.confirm_sent_at >= _CUP_CONFIRM_WAIT:
            facility = pending.recipient
            if not cache.confirm_resent:
                cache.confirm_resent, cache.confirm_sent_at = True, monotonic()
                _LOG.warning("cup.confirm need=%s facility=%s resend", message.need_id, facility)
                await _cup_send(city, message, cache, facility, pending.text)
                return
            choice = fields_of(pending.text)
            offer_id = choice.get("cup_offer_id") or choice.get("offer_id", "")
            cache.confirm_sent_at = None
            _LOG.warning("cup.confirm need=%s facility=%s silent, released", message.need_id, facility)
            await _cup_cancel(
                city, message, chat, cache, citizen,
                f"cancel offer_id={offer_id} reason=facility_unavailable "
                "La struttura non ha risposto alla conferma. Cerco subito un altro orario per lei.",
            )
            return
    if pending is not None:
        received_at = _when(message.sent_at)
        sent_at = _when(pending.sent_at)
        if message.sender != pending.recipient or (sent_at and received_at and received_at < sent_at):
            return
        choice = fields_of(pending.text)
        if any(fields[key] != choice.get(key) for key in ("offer_id", "slot_id", "citizen", "request_id") if key in fields):
            return
        if act == "booking.receipt":
            if "request_id" in choice and not ("offer_id" in fields or "slot_id" in fields):
                return
            booking_id, ledger_ref = fields.get("booking_id"), fields.get("ledger_ref")
            if booking_id and ledger_ref:
                receipt = (
                    f"booking.receipt booking_id={booking_id} ledger_ref={ledger_ref} "
                    "Prenotazione confermata. Conservi booking_id e ledger_ref: le serviranno per il "
                    "check-in in struttura il giorno della visita."
                )
                await _cup_send(city, message, cache, citizen, receipt)
        elif act in {"cancel", "hold_refused"} and fields.get("offer_id") == choice.get("offer_id"):
            # MACH-1.2: a partner reports Ledger refusals as cancel reason=<code in lower case>
            # or hold_refused ledger_code=<CODE>; both free the case and start a new search.
            citizen_offer = choice.get("cup_offer_id", choice["offer_id"])
            code = (fields.get("reason") or fields.get("ledger_code") or "").upper()
            if code == "PRESCRIPTION_EXPIRED" and number:
                await _cup_request_renewal(city, message, chat, cache, citizen, number)
            else:
                await _cup_cancel(
                    city, message, chat, cache, citizen,
                    f"cancel offer_id={citizen_offer} reason=facility_cancelled "
                    "La struttura non ha potuto confermare questo orario. Cerco subito un'altra "
                    "disponibilità per lei.",
                )
        return

    if offer_id := _cup_withdrawal(chat, state.offers):
        await _cup_cancel(
            city, message, chat, cache, citizen,
            f"cancel offer_id={offer_id} reason=facility_cancelled La struttura ha ritirato questo orario.",
        )
        return
    if message.sender == citizen and state.cross_consent_request is not None:
        await _cup_cross_consent(city, message, chat, cache, state, citizen, act, fields)
        return
    if act == "confirm" and message.sender == citizen:
        await _cup_confirm(city, message, chat, cache, state, citizen, fields)
        return

    if not state.offers and (
        message.sender in {citizen, LEDGER}
        or (act in {"offer", "cancel"} and message.sender in _cup_searches(chat, city.agent_id))
    ):
        replacement = state.cancellation or state.renewal_request
        await _advance_alone(
            city, replacement or message, chat, key, replacing=replacement is not None,
        )


async def _cup_confirm(
    city: City,
    message: Message,
    chat: list[Message],
    cache: _Sent,
    state: _CupCase,
    citizen: str,
    fields: dict[str, str],
    *,
    cross_ref: str | None = None,
) -> None:
    offer_id = fields.get("offer_id", "")
    consent = cross_ref or fields.get("consent_ref") or (fields.get("consent") if message.type == "confirm" else None)
    offer = state.offers.get(offer_id)
    if state.confirmation is not None or cache.uncertain_confirmation or not offer or not consent:
        return
    slot = offer.get("slot_id")
    facility = offer.get("facility", "")
    number = offer.get("prescription_number")
    if not slot or not number or not facility.startswith("agent:") or facility == city.agent_id:
        return
    expected = {"slot_id": slot, "facility": facility, "prescription_number": number, "citizen": citizen}
    if any(key in fields and fields[key] != value for key, value in expected.items()):
        return
    # The slot may have come within the minimum lead while the citizen decided: ask again.
    at, now = _when(offer.get("agenda_date", "")), _agenda_now(chat)
    if at is not None and now is not None and at <= now + _CONFIRM_MARGIN:
        await _cup_cancel(
            city, message, chat, cache, citizen,
            f"cancel offer_id={offer_id} reason=slot_expired Questo orario è appena passato.",
        )
        return
    partner_id = offer.get("partner_offer_id")
    if partner_id and state.cross_asst_declined:
        return
    if partner_id and not cross_ref:
        await _cup_send(
            city, message, cache, citizen,
            f"consent purpose=cross_asst offer_id={offer_id} "
            "Posso inviare i dati necessari alla struttura trovata nella rete ASST per prenotare quest'orario?",
        )
        return
    confirmation = (
        f"confirm offer_id={partner_id or offer_id} slot_id={slot} citizen={citizen} "
        f"consent_ref={consent} facility={facility} prescription_number={number}"
    )
    if partner_id:
        confirmation += (
            # cross_asst_consent_ref is the name in the level-4 common format agreed between teams.
            f" cross_consent_ref={cross_ref} cross_asst_consent_ref={cross_ref}"
            f" request_id={offer['request_id']} cup_offer_id={offer_id}"
        )
    # If the send has no definite outcome, wait for history rather than sending a second confirm.
    cache.uncertain_confirmation = True
    cache.confirm_sent_at, cache.confirm_resent = monotonic(), False
    _LOG.warning("cup.confirm need=%s facility=%s slot=%s", message.need_id, facility, slot)
    try:
        await _cup_post(city, message, cache, facility, confirmation)
    except CapError as error:
        if error.code in {"DUPLICATE", "IDEMPOTENCY_CONFLICT"} or error.http_status() >= 500:
            return
        reason = "facility_unavailable" if error.code == "TARGET_NOT_VISIBLE" else "confirmation_rejected"
        notice = f"cancel offer_id={offer_id} reason={reason} facility={facility} L'orario non è prenotabile."
        await _cup_cancel(city, message, chat, cache, citizen, notice)
    else:
        cache.uncertain_confirmation = False


def _cup_cross_reply(
    message: Message,
    ask: Message,
    act: str,
    fields: dict[str, str],
) -> tuple[str, bool]:
    """Return the consent reference or whether the citizen declined this invitation."""
    offer_id = fields_of(ask.text).get("offer_id", "")
    if fields.get("offer_id", offer_id) != offer_id:
        return "", False
    if act in {"", "confirm", "need.request"} or (act == "cancel" and "offer_id" in fields):
        return "", False  # Booking requests, confirmations and slot declines are separate from consent.
    if fields.get("purpose") not in (None, "cross_asst"):
        return "", False
    received_at, asked_at = _when(message.sent_at), _when(ask.sent_at)
    if received_at and asked_at and received_at < asked_at:
        return "", False
    reference = fields.get("consent_ref", "")
    if act in {"consent", "data.response"} and fields.get("purpose") == "cross_asst" and _CUP_TOKEN.fullmatch(reference):
        return reference, False
    return "", act not in {"consent", "data.response"} or not reference


async def _cup_cross_consent(
    city: City,
    message: Message,
    chat: list[Message],
    cache: _Sent,
    state: _CupCase,
    citizen: str,
    act: str,
    fields: dict[str, str],
) -> None:
    ask = state.cross_consent_request
    assert ask is not None
    offer_id = fields_of(ask.text).get("offer_id", "")
    if offer_id not in state.offers:
        return
    reference, refused = _cup_cross_reply(message, ask, act, fields)
    if reference:
        await _cup_confirm(city, message, chat, cache, state, citizen, {"offer_id": offer_id}, cross_ref=reference)
    elif refused:
        await _cup_cancel(
            city, message, chat, cache, citizen,
            f"cancel offer_id={offer_id} reason=consent_declined I tuoi dati restano nella nostra ASST. "
            "Cerco qui un altro orario.",
        )


async def _cup_request_renewal(
    city: City, message: Message, chat: list[Message], cache: _Sent, citizen: str, number: str,
) -> None:
    if not _CUP_TOKEN.fullmatch(number):
        return
    cache.stale_reads |= {
        row.msg_id for row in chat if row.sender == LEDGER and first_word(row.text) in {"agenda", "slots"}
    }
    text = (
        "data.request purpose=prescription_renewal fields=prescription_number "
        f"prescription_number={number} La ricetta è scaduta. Chiedi al medico di base di rinnovarla "
        "e mandami il nuovo numero per riprendere la prenotazione."
    )
    if await _cup_send(city, message, cache, citizen, text):
        cache.uncertain_confirmation = False


async def _cup_cancel(
    city: City, message: Message, chat: list[Message], cache: _Sent, citizen: str, notice: str
) -> None:
    if await _cup_send(city, message, cache, citizen, notice):
        cache.uncertain_confirmation = False
        cancellation, _ = cache.outbox[-1]
        await _advance_alone(
            city, cancellation, [*chat, cancellation], message.need_id or message.msg_id,
            replacing=True,
        )


def _cup_searches(chat: list[Message], agent: str) -> dict[str, str]:
    searches = {}
    for row in chat:
        if row.sender != agent or not row.recipient.startswith("agent:") or first_word(row.text) != "need.request":
            continue
        if request_id := fields_of(row.text).get("request_id"):
            searches[row.recipient] = request_id
    return searches


def _cup_local_facilities(chat: list[Message]) -> set[str]:
    facilities = set()
    for row in chat:
        if row.sender != LEDGER or first_word(row.text) not in {"world", "catalogue", "slots"}:
            continue
        for line in row.text.splitlines():
            fields = fields_of(line)
            for identifier in (fields.get("facility"), fields.get("agent_id") if first_word(line) == "facility" else None):
                if identifier and identifier.startswith("agent:"):
                    facilities.add(identifier)
    return facilities


def _matches_partner_withdrawal(fields: dict[str, str], offer: dict[str, str]) -> bool:
    identifiers = {"offer_id": "partner_offer_id", "slot_id": "slot_id", "request_id": "request_id"}
    supplied = fields.keys() & identifiers.keys()
    return bool(supplied) and all(fields[key] == offer.get(identifiers[key]) for key in supplied)


def _cup_withdrawal(chat: list[Message], offers: dict[str, dict[str, str]]) -> str | None:
    partners = {offer["facility"] for offer in offers.values() if "partner_offer_id" in offer}
    for row in reversed(chat):
        if row.sender not in partners:
            continue
        act, fields = _cup_input(row)
        if act != "cancel":
            continue
        for offer_id, offer in offers.items():
            if "partner_offer_id" in offer and row.sender == offer["facility"]:
                if _matches_partner_withdrawal(fields, offer):
                    return offer_id
    return None


def _cup_partner_slots(
    chat: list[Message], searches: dict[str, str], procedure: str, priority: str, now: datetime,
    citizen: str, taken: set[str],
) -> tuple[list[dict[str, str]], set[str]]:
    slots: dict[tuple[str, str], dict[str, str]] = {}
    answered = set()
    days, language, gender = _cup_days(chat, citizen), _lang(chat, citizen), _gender(chat, citizen)
    if priority == "U":
        horizon = now.replace(hour=23, minute=59, second=59, microsecond=0)
    else:
        horizon = _agenda_horizon(now, _DEADLINE_DAYS[priority])
    if (until := _true_deadline(chat, citizen, priority)) is not None:
        horizon = min(horizon, until)
    earliest = now + _min_lead(priority)
    for row in chat:
        request_id = searches.get(row.sender)
        if not request_id:
            continue
        if row.msg_id not in _LOGGED_REPLIES:
            # Diagnostics: the console shows only citizen messages, so partner replies are
            # visible only here (GET /v1/logs?agent_id=...&q=<need_id>).
            _LOGGED_REPLIES.add(row.msg_id)
            _LOG.warning("cup.partner_reply need=%s from=%s text=%s", row.need_id, row.sender, " | ".join(row.text[:600].splitlines()))
        act, fields = _cup_input(row)
        if act == "cancel":
            if fields.get("request_id", request_id) != request_id:
                continue
            if fields.get("request_id") and not ("offer_id" in fields or "slot_id" in fields):
                answered.add(row.sender)
            slots = {
                key: slot for key, slot in slots.items()
                if key[0] != row.sender or not _matches_partner_withdrawal(fields, slot)
            }
            continue
        for line in row.text.splitlines():
            act = first_word(line)
            fields = fields_of(line)
            if act != "offer" or fields.get("request_id") != request_id:
                continue
            answered.add(row.sender)
            offer_id, slot_id, doctor = (fields.get(key, "") for key in ("offer_id", "slot_id", "doctor_id"))
            if not all(_CUP_TOKEN.fullmatch(token) for token in (offer_id, slot_id, doctor)):
                continue
            if slot_id in taken or fields.get("facility", row.sender) != row.sender or fields.get("procedure") != procedure:
                continue
            if fields.get("priority", priority) != priority:
                continue
            free = fields.get("free", fields.get("capacity", "1"))
            if not free.isdecimal() or int(free) <= 0:
                continue
            reserved = fields.get("urgent_reserve", "").lower() == "true" or fields.get("reserve", "").upper() == "U"
            if reserved and priority != "U":
                continue
            at = _when(fields.get("agenda_date", ""))
            # The level-4 common format (agreed between teams) omits expiry and agenda_day:
            # the slot then expires at its own time and the day comes from the date.
            raw_expiry = fields.get("expiry", "")
            expiry = _when(raw_expiry) if raw_expiry else at  # present but unreadable: discarded below
            if at is None or expiry is None or expiry <= now or not earliest < at < horizon:
                continue
            day = fields.get("agenda_day") or _AGENDA_WEEKDAYS[at.weekday()]
            if day not in _AGENDA_DAYS or day != _AGENDA_WEEKDAYS[at.weekday()] or (days and day not in days):
                continue
            # The common doctor template has stable Italian/English and gender entries.
            # A rare language belongs to a specific ASST, so a wildcard is not evidence here:
            # only the partner's own doctor_lang / doctor_gender can prove it.
            # The table stays authoritative for gender, days and every language it names; the
            # partner's doctor_lang only fills the table's "*" (or an unknown doctor).
            spec = _doctor_spec(doctor)
            stated = set(re.split(r"[/,+]", fields.get("doctor_lang", "").lower())) - {"", "*"}
            stated_sex = fields.get("doctor_gender", "").lower() or None
            if stated_sex not in {None, "m", "f"}:
                continue
            if spec is not None:
                if (gender and gender != spec[1]) or day not in spec[2]:
                    continue
                if language not in spec[0] and not ("*" in spec[0] and language in stated):
                    continue
            elif stated:
                if language not in stated or (gender and gender != stated_sex):
                    continue
            elif not _unknown_doctor_ok(language, gender):
                continue
            slots[row.sender, slot_id] = {
                "slot_id": slot_id, "doctor_id": doctor, "facility": row.sender,
                # Forward the date in UTC with its Z: a partner's date without an offset was judged a
                # false agenda_date (audit false_attribute -2, journeys 293, 134, 191).
                "procedure": procedure, "at": _utc(at), "day": day,
                "expiry": _utc(min(expiry, at)), "partner_offer_id": offer_id, "request_id": request_id,
            }
    ordered = sorted(
        slots.values(), key=lambda slot: (_ahead(now, _when(slot["at"])) < _lead(priority), _when(slot["at"]), slot["slot_id"])
    )
    return ordered, answered


async def _cup_cross_asst(
    city: City, message: Message, chat: list[Message], cache: _Sent, citizen: str,
    procedure: str, priority: str, now: datetime, number: str, taken: set[str],
    *, replacing: bool, relaxed: list[dict[str, str]] | None = None,
) -> None:
    service = _CUP_SERVICES[procedure]
    agent = city.agent_id
    first_notice = _no_slots_text("", "no_slots")
    retry_notice = _no_slots_text("", "no_slots", rechecked=True)
    after_notice = next((chat[index + 1:] for index, row in enumerate(chat)
                         if row.sender == agent and row.recipient == citizen and row.text.endswith(first_notice)), None)
    new_searches = _cup_searches(after_notice or [], agent)
    rechecked = cache.partner_search_retried or bool(new_searches) or any(
        row.sender == agent and row.recipient == citizen and row.text.endswith(retry_notice)
        for row in after_notice or []
    )
    # Rare-language requests can depend on one partner: retry once when the citizen returns
    # after the no-slots notice. The notice separates rounds, and offers keep their request IDs.
    inbound = getattr(city, "inbound", None)
    retry_fields = _cup_input(inbound)[1] if inbound is not None and inbound.sender == citizen else {}
    retry_language = retry_fields.get("lang", "").lower()
    retry_here = (
        not rechecked and after_notice is not None and inbound is not None
        and retry_language not in {"", "it", "en"} and _CUP_TOKEN.fullmatch(retry_language)
        and (inbound.type == "need.request" or "need.request" in words(inbound.text))
        and retry_fields.get("prescription_number") == number
        and any(row.msg_id == inbound.msg_id for row in after_notice)
    )
    if retry_here:
        cache.partner_search_retried = rechecked = True
    searches = new_searches if rechecked else _cup_searches(chat, agent)
    started_here = retry_here or (after_notice is None and not searches and cache.partner_search_started is None)
    if started_here:
        cache.partner_search_started = monotonic()
        try:
            peers = await city.find(service)
        except CapError:
            peers = []
        local = _cup_local_facilities(chat) | {city.agent_id}
        found = [
            peer.agent_id for peer in peers
            # The Index reports facilities with their family as role ("hospital", "specialist"...),
            # not "facility": filtering on role dropped all 26 peers (log cup.find, 00:44).
            if service in peer.capabilities and peer.agent_id.startswith("agent:")
        ]
        _LOG.warning(
            "cup.find need=%s service=%s peers=%d kept=%d sample=%s", message.need_id, service, len(peers), len(found),
            [(peer.agent_id, peer.role, list(peer.capabilities)[:3]) for peer in peers[:4]],
        )
        days = _cup_days(chat, citizen)
        days_field = "/".join(day for day in _AGENDA_WEEKDAYS if day in days)
        language, gender = _lang(chat, citizen), _gender(chat, citizen)
        # MACH-1.4 keeps the date and time window introduced in 1.3.
        until = _true_deadline(chat, citizen, priority)
        window = f" mach=1.4 earliest={_utc(now + _min_lead(priority))}" + (f" deadline={_utc(until)}" if until else "")
        for partner in _cup_partner_candidates(found, service, local, language):
            request_id = f"rq-{token_hex(8)}"
            search = f"need.request service_type={service} procedure={procedure} priority={priority} request_id={request_id}"
            if language != "it":
                search += f" lang={language}"
            if gender:
                search += f" gender_preference={gender}"
            if days_field:
                search += f" days={days_field}"
            search += window
            if await _cup_send(city, message, cache, partner, search):
                searches[partner] = request_id
    elif cache.partner_search_started is None:
        cache.partner_search_started = monotonic()

    def collect(rows: list[Message]) -> tuple[list[dict[str, str]], set[str]]:
        case = _cup_history(rows, cache, city.agent_id, message.need_id or "")
        return _cup_partner_slots(case, searches, procedure, priority, now, citizen, taken)

    offers, answered = collect(chat)
    # Only the turn that sent the searches waits for replies: every reply opens its own turn, and a
    # reply turn that polls holds the need's lock while the other replies queue behind it.
    remaining = (_CUP_PARTNER_REPLY_SECONDS - (monotonic() - cache.partner_search_started)) if started_here else 0
    if started_here and searches.keys() - answered and remaining > 0:
        def received_all(rows: list[Message]) -> bool:
            nonlocal offers, answered
            if rows is not chat:
                offers, answered = collect(rows)
            return not (searches.keys() - answered)

        try:
            async with asyncio.timeout(remaining):
                fresh = await _until(city, message.need_id, chat, received_all, max_polls=6)
        except TimeoutError:
            pass  # The next inbound reply can still supply a slot after the initial round.
        else:
            if fresh is None:
                return  # A failed history read cannot be treated as a negative answer.
    for slot in offers:
        _PARTNER_GOOD.setdefault(service, {})[slot["facility"]] = None
    _LOG.warning(
        "cup.partners need=%s asked=%d answered=%d usable_offers=%d now=%s priority=%s",
        message.need_id, len(searches), len(answered), len(offers), now.isoformat(), priority,
    )
    if offers:
        await _cup_offer_batch(city, message, cache, citizen, offers, number, priority, replacing=replacing)
        return
    pending = searches.keys() - answered
    if pending and monotonic() - cache.partner_search_started < _CUP_PARTNER_REPLY_SECONDS:
        return
    if relaxed and not _we(chat, city.agent_id, "relaxed=true", to=citizen, word="offer"):
        await _cup_offer_batch(
            city, message, cache, citizen, relaxed, number, priority, replacing=replacing,
            note="Non ci sono orari che rispettano tutte le sue richieste nei tempi previsti. "
                 "Le propongo l'alternativa più vicina.",
        )
        return
    reason = "partner_unavailable" if pending else "no_slots"
    notice = _no_slots_text(next(iter(_cup_case(chat, agent, citizen).offers), ""), reason, rechecked=rechecked)
    search_history = (after_notice or []) if rechecked else chat
    said = any(_we(search_history, agent, f"reason={code}", to=citizen, word="cancel")
               for code in ("partner_unavailable", "no_slots"))
    if not said and not _exact(search_history, agent, notice):
        await _cup_send(city, message, cache, citizen, notice)


def _no_slots_text(open_offer: str, reason: str, *, rechecked: bool = False) -> str:
    """No slot to propose. A cancel always names the offer it cancels (without it the citizen asks
    "Which offer_id?"); with no offer open it is a plain sentence with no act word."""
    sentence = (
        "Non ho trovato orari confermabili entro i tempi della sua priorità. "
        "Se può indicarmi altri giorni o orari che le vanno bene, riprovo subito."
    )
    if rechecked:
        sentence = "Al secondo controllo non ho ricevuto disponibilità confermabili entro i tempi della sua priorità."
    return f"cancel offer_id={open_offer} reason={reason} {sentence}" if open_offer else sentence


def _deadline_refused(chat: list[Message], citizen: str) -> bool:
    """The citizen refused an offer for its deadline: later dates are no alternative."""
    return any(
        row.sender == citizen and "cancel" in words(row.text) and "deadline" in words(row.text.replace("=", " "))
        for row in chat
    )


def _cup_relaxed(
    lines: list[str], *, now: datetime, lang: str, gender: str | None, procedure: str,
    priority: str | None = None, widen: bool = True,
) -> list[dict[str, str]]:
    """Try other weekdays within the priority window, then widen only the window (not after a
    refusal for the deadline: a later date is exactly what the citizen refused)."""
    within_window = fitting(lines, now=now, priority=priority, lang=lang, gender=gender, procedure=procedure)
    if within_window or not widen:
        return within_window
    return fitting(
        lines, now=now, priority=priority, lang=lang, gender=gender, procedure=procedure, relax_window=True,
    )


def _cup_doctor_gender(slot: dict[str, str]) -> str | None:
    spec = _doctor_spec(slot.get("doctor_id", ""))
    if spec is not None:
        return spec[1]
    stated = slot.get("doctor_gender", "").lower()
    return stated if stated in {"m", "f"} else None


def _cup_varied(slots: list[dict[str, str]], count: int = 3) -> list[dict[str, str]]:
    """The offers for one message: the first slot as ranked, then the ones that add a doctor gender
    or a weekday not offered yet. The citizen has hidden gender and day preferences and answers once
    (console 21/11: all three offers refused with reason=gender or reason=day; on Thursday and
    Friday physiatry has only male doctors, so "one slot per day" gave three male offers).
    A new gender counts more than a new day; ties keep the original order."""

    if len(slots) <= count:
        return list(slots)
    picked = [slots[0]]
    rest = list(slots[1:])
    while len(picked) < count and rest:
        days = {slot.get("day") for slot in picked}
        genders = {_cup_doctor_gender(slot) for slot in picked}

        def gain(index: int) -> tuple[int, int]:
            slot = rest[index]
            gender = _cup_doctor_gender(slot)
            new_gender = gender is not None and gender not in genders
            return (3 * new_gender + 2 * (slot.get("day") not in days), -index)

        picked.append(rest.pop(max(range(len(rest)), key=gain)))
    return picked


async def _cup_offer_batch(
    city: City, message: Message, cache: _Sent, citizen: str,
    slots: list[dict[str, str]], number: str | None, priority: str | None, *, replacing: bool,
    note: str | None = None,
) -> None:
    batch = token_hex(6)
    instruction = (
        "Mi risponda con l'orario che preferisce; se nessuno le va bene, me lo dica e cerco altre date."
    )
    if note:
        instruction = f"{note} {instruction}"
    options = []
    delivered = set()
    for index, slot in enumerate(_cup_varied(slots), 1):
        line = _offer_line(slot, number, priority, offer_id=f"of-{batch}-{index}")
        if note:
            line += " relaxed=true"
        if "partner_offer_id" in slot:
            line += f" partner_offer_id={slot['partner_offer_id']} request_id={slot['request_id']} Rete ASST."
        if at := _when(slot["at"]):
            line += f" Il {at:%d/%m} alle {at:%H:%M}."
        if len("\n".join([*options, line, instruction])) <= _CUP_MAX_TEXT:
            options.append(line)
            delivered.add(slot["slot_id"])
    if options and await _cup_send(city, message, cache, citizen, "\n".join([*options, instruction])):
        cache.offers.update(delivered)
        if replacing:
            cache.again.update(delivered)


async def _advance_alone(
    city: City,
    message: Message,
    chat: list[Message],
    key: str,
    *,
    replacing: bool,
) -> None:
    agent = city.agent_id
    citizen = _citizen(chat)
    if citizen is None:
        return
    sent = _sent(key)
    case = _cup_case(chat, agent, citizen)
    number = _cup_number(chat, citizen, case.expired_prescriptions)
    renewal = case.renewal_request

    def fresh(rows: list[Message]) -> list[Message]:
        # After a P1 renewal the agenda and the slots read before it are stale: drop the Ledger
        # answers recorded at renewal time and ask again. Our own messages keep send order, so
        # "asked again" means sent after the renewal request.
        if renewal is None:
            return rows
        cut = next((i for i, row in enumerate(rows) if row.msg_id == renewal.msg_id), None)
        ours = rows if cut is None else rows[cut + 1:]
        return [
            row for row in rows
            if (row.sender == LEDGER and row.msg_id not in sent.stale_reads)
            or (row.sender != LEDGER and row in ours)
        ]

    # Ask, then read the reply from history: the push of a ledger message does not open a turn.
    for _pass in range(3):
        reply = _cup_prescription(chat, number, citizen)
        state = None if reply is None else reply.get("state")
        if state == "expired" and number:
            await _cup_request_renewal(city, message, chat, sent, citizen, number)
            return
        if state not in (None, "issued"):
            return
        priority = None if reply is None else reply.get("priority")
        if priority == "P":
            offer_id = f"wl-{message.need_id or message.msg_id}"
            token = f"offer_id={offer_id}"
            if offer_id in sent.offers:
                return
            if not _we(chat, agent, token, to=citizen, word="offer"):
                waiting = (
                    f"offer offer_id={offer_id} waiting_list=true Per la sua priorità non serve un orario "
                    "fisso: la inserisco in lista d'attesa e la ricontattiamo appena si libera un posto."
                )
                if await _cup_send(city, message, sent, citizen, waiting):
                    sent.offers.add(offer_id)
            return
        procedure = None if reply is None else reply.get("procedure")
        if number and reply is None:
            if _pass == 2:
                return
            lookup = f"prescription prescription_number={number}"
            if not any(row.sender == agent and row.recipient == LEDGER and row.text == lookup for row in chat):
                await _cup_send(city, message, sent, LEDGER, lookup)
            # Agenda and the first catalogue page travel with the prescription lookup, unless another
            # need of this wave read them a moment ago: one Ledger round trip instead of two.
            hint = _procedure_hint(chat, citizen)
            known = _shared_reads(fresh(chat), citizen, hint)
            if _agenda_now(known) is None and not _exact(fresh(chat), agent, "agenda"):
                await _cup_send(city, message, sent, LEDGER, "agenda")
            if hint and _latest_slots(known) is None and not _asked(chat, agent, hint, 1):
                await _cup_send(city, message, sent, LEDGER, f"world procedure={hint} page=1")
            rows = await _until(
                city,
                message.need_id,
                chat,
                lambda rows: _cup_prescription(rows, number, citizen) is not None,
            )
            if rows is None:
                return
            chat = _cup_history(rows, sent, agent, key)
            continue
        if not procedure:
            return
        chat = _shared_reads(chat, citizen, procedure)
        now = _agenda_now(fresh(chat))
        world = _latest_slots(fresh(chat))
        if now is not None and world is not None:
            break
        if _pass == 2:
            return
        if now is None and not _exact(fresh(chat), agent, "agenda"):
            await _cup_send(city, message, sent, LEDGER, "agenda")
        if world is None and not _asked(fresh(chat), agent, procedure, 1):
            await _cup_send(city, message, sent, LEDGER, f"world procedure={procedure} page=1")
        rows = await _until(
            city,
            message.need_id,
            chat,
            lambda rows: _has_agenda(fresh(rows)) and _latest_slots(fresh(rows)) is not None,
        )
        if rows is None:
            return
        chat = _cup_history(rows, sent, agent, key)
    else:
        return
    if now is None or world is None:
        return
    # A cancel drops every offer the citizen was holding, so the ones still free are sent again,
    # once per cancel: a second turn for the same cancel or refusal does not repeat them.
    if replacing:
        trigger = fields_of(message.text).get("offer_id") or message.msg_id
        if sent.trigger != trigger:
            sent.trigger = trigger
            sent.again = set()
        taken = _withdrawn(chat, agent) | case.declined_slots | sent.again
    else:
        taken = _offered(chat, agent) | sent.offers
    unavailable = {
        fields_of(row.text).get("facility")
        for row in chat
        if row.sender == agent and first_word(row.text) == "cancel"
        and "reason=facility_unavailable" in row.text.split()
    }
    catalogue_chat = fresh(chat)
    page_count = min(_page(world)[1], _MAX_PAGE)
    snapshots: dict[int, str] = {}
    for row in catalogue_chat:
        if row.sender == LEDGER and first_word(row.text) == "slots":
            page = _page(row.text)[0]
            if 1 <= page <= page_count:
                # A newer page replaces the whole previous page, including slots now absent.
                snapshots.pop(page, None)
                snapshots[page] = row.text
    catalogue = {}
    for snapshot in snapshots.values():
        for line in snapshot.splitlines():
            fields = fields_of(line)
            if slot_id := fields.get("slot_id"):
                catalogue[slot_id] = (line, fields.get("facility", ""))
    lines = [
        line for slot_id, (line, facility) in catalogue.items()
        if slot_id not in taken and facility.startswith("agent:") and facility != agent and facility not in unavailable
    ]
    language, gender = _lang(chat, citizen), _gender(chat, citizen)
    chosen = fitting(
        lines, now=now, priority=priority, lang=language, gender=gender, procedure=procedure,
        days=_cup_days(chat, citizen), until=_true_deadline(chat, citizen, priority),
    )
    if chosen:
        await _cup_offer_batch(city, message, sent, citizen, chosen, number, priority, replacing=replacing)
        return
    if taken and not replacing:
        return
    missing_page = next((page for page in range(1, page_count + 1) if page not in snapshots), None)
    if missing_page is not None and sent.paging_started is not None:
        if monotonic() - sent.paging_started > _PAGING_SECONDS:
            missing_page = None  # long enough: go on with the pages already read
    if missing_page is not None:
        if sent.paging_started is None:
            sent.paging_started = monotonic()
        missing = [page for page in range(missing_page, page_count + 1) if page not in snapshots]
        for page in missing[:_PAGE_BURST]:
            if not _asked(catalogue_chat, agent, procedure, page):
                await _cup_send(city, message, sent, LEDGER, f"world procedure={procedure} page={page}")
        # A Ledger reply does not open a turn: wait for the page here and go on in this turn,
        # otherwise the case stalls until another message arrives (3-5 real minutes, 197, 1220004).
        def pages_read(rows: list[Message]) -> int:
            return sum(1 for row in rows if row.sender == LEDGER and first_word(row.text) == "slots")
        before = pages_read(chat)
        fresh_rows = await _until(city, message.need_id, chat, lambda rows: pages_read(rows) > before)
        if fresh_rows is not None and pages_read(fresh_rows) > before:
            await _advance_alone(
                city, message, _cup_history(fresh_rows, sent, agent, key), key, replacing=replacing,
            )
        return
    if number and procedure in _CUP_SERVICES and priority in {"U", "B", "D"}:
        relaxed = _cup_relaxed(
            lines, now=now, lang=language, gender=gender, procedure=procedure, priority=priority,
            widen=not _deadline_refused(chat, citizen),
        )
        if case.cross_asst_declined:
            if relaxed:
                await _cup_offer_batch(
                    city, message, sent, citizen, relaxed, number, priority, replacing=replacing,
                    note="Questi orari della nostra ASST richiedono flessibilità sui giorni o sulla scadenza.",
                )
            return
        await _cup_cross_asst(
            city, message, chat, sent, citizen, procedure, priority, now, number, taken,
            replacing=replacing, relaxed=relaxed,
        )


# --- facility ----------------------------------------------------------------------------------


