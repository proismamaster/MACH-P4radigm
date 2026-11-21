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
from collections import OrderedDict
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import monotonic

from city_sdk.city import LEDGER, CapError, City, Message, Need, OutOfScope, clinical, understood

ROLES = ("booking_centre", "gp", "hospital", "specialist_care", "family_counseling")
_MAX_PAGE = 8
# One real minute is one agenda hour and a citizen answers after 3-27 minutes (console 21/11): a slot a few
# hours ahead is already past when it decides (`reason=past`, Ledger `EXPIRED`). Slots at least _LEAD ahead
# in agenda time come first, then the ones at least _MIN_LEAD ahead; nearer ones are never offered.
_LEAD = timedelta(hours=30)
_MIN_LEAD = timedelta(hours=10)  # tools/sim_percorsi.py: best minimum; consultorio citizens wait up to 34 min
_MIN_LEAD_U = timedelta(hours=4)


def _min_lead(priority: str | None) -> timedelta:
    return _MIN_LEAD_U if priority == "U" else _MIN_LEAD
# Doctor key (the last segment of doctor_id) -> languages, gender, days. ``*`` is the ASST's
# rare language. The Ledger's slot line names the doctor; it does not repeat this table.
_DOCTORS: dict[str, tuple[frozenset[str], str, frozenset[str]]] = {
    "h1": (frozenset({"it", "en"}), "f", frozenset({"mon", "tue", "wed"})),
    "h2": (frozenset({"it"}), "m", frozenset({"wed", "thu", "fri"})),
    "h3": (frozenset({"it", "*"}), "m", frozenset({"tue", "thu"})),
    "s1": (frozenset({"it", "en"}), "m", frozenset({"mon", "wed", "fri"})),
    "s2": (frozenset({"it"}), "f", frozenset({"tue", "thu"})),
    "c1": (frozenset({"it", "en"}), "f", frozenset({"mon", "tue", "wed", "thu", "fri"})),
}
_DEADLINE_DAYS = {"B": 2, "D": 5}


def _agenda_horizon(now: datetime, days: int) -> datetime:
    """``now`` plus ``days`` days of AGENDA. Saturday and Sunday do not exist in the agenda: after
    Friday it goes on from Monday (kit, ADR-124). B on a Thursday ends on Monday, not on Saturday."""

    at = now
    left = days
    while left > 0:
        at += timedelta(days=1)
        if at.weekday() < 5:
            left -= 1
    return at


_LOG = logging.getLogger("care")
# The Relay accepts a ledger reply and then the agent rejects the push, so the reply sits in
# the case history and never opens a turn. Wait briefly and read it back from history.
_PULL_TRIES = 24
_PULL_PAUSE = 0.25
# Needs whose sent offers this process remembers; the oldest is forgotten first.
_SENT_NEEDS = 4096


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


# Trust ring, safe mode (level 8, impostors from Saturday 10:00). The Index may not return the
# booking centres to a facility, so a stranger is NOT refused for being unknown: a sender is
# blocked (no reply, no Ledger call) only when it is in neither the ring list nor city.find AND
# it sends a facility= naming another agent or a text with instructions. Before 10:00 nothing is
# blocked and the log says who would have been. The list holds the ids published so far.
_RING = frozenset((
    "agent:h6r1v45esk77", "agent:hnpe58epeyh1", "agent:gpr1zqe343gb", "agent:zand0f57ec1j",
    "agent:nanpr5mgm2py", "agent:pky3vqyqbepa", "agent:xtj1dk9x3qej", "agent:q18es2d82f8r",
    "agent:x0vr9rbwpesr", "agent:h8425ac7btd8", "agent:tmt0bcv0st1f", "agent:n9bf9y6670hp",
    "agent:s1twcdzg3296", "agent:f2s88vwd3jnf", "agent:gxq3vzgt3h5t", "agent:tty8erdj6t41",
    "agent:etpwrfmfa8hm", "agent:tnzkhsa62kn0",
))
_KNOWN: dict[str, float] = {}  # booking centre -> when city.find last confirmed it
_KNOWN_FOR = 300.0
_FIND_EVERY = 5.0  # an unknown sender cannot make us query the Index more often than this
_found_at = [-_FIND_EVERY]


async def _in_ring(city: City, sender: str) -> bool:
    if sender in _RING or _KNOWN.get(sender, 0.0) > monotonic():
        return True
    if monotonic() - _found_at[0] < _FIND_EVERY:
        return False
    _found_at[0] = monotonic()
    try:
        peers = await city.find("booking_centre")
    except CapError:
        return False
    for peer in peers:
        if peer.role == "booking_centre" or any(c.split(".")[0] == "booking_centre" for c in peer.capabilities):
            _KNOWN[peer.agent_id] = monotonic() + _KNOWN_FOR
    return _KNOWN.get(sender, 0.0) > monotonic()


# Real clock, Milan time (CET, UTC+1): the impostors arrive on Saturday 21/11 at 10:00.
_ENFORCE_FROM = datetime(2026, 11, 21, 10, 0, tzinfo=timezone(timedelta(hours=1)))
_INJECTION = re.compile(
    r"ignor\w*\s+(\w+\s+){0,3}(regole|istruzioni|rules|instructions|prompt)"
    r"|(disregard|forget|dimentica\w*)\s+(\w+\s+){0,3}(rules|instructions|regole|istruzioni)"
    r"|\b(sei ora|you are now|act as|fingi di)\b|system prompt"
    r"|(mandami|inviami|dammi|mostrami|send me|give me|reveal)\s+(\w+\s+){0,3}(dati|data|nome|name)"
    r"|senza (il )?consenso|without (the )?consent|salta\w* i controlli|bypass",
    re.IGNORECASE,
)


async def _admitted(city: City, message: Message) -> bool:
    sender = message.sender
    if sender == LEDGER or sender == city.agent_id or sender.startswith(("citizen:", "city:")):
        return True
    # facility= names the sender (its own offer) or us (the booking centre's confirm); another
    # agent is a forged claim.
    facility = _search_fields(message).get("facility", "")
    forged = bool(facility) and facility not in (sender, city.agent_id)
    injected = bool(_INJECTION.search(message.text))
    if not (forged or injected) or await _in_ring(city, sender):
        return True
    enforced = datetime.now(timezone.utc) >= _ENFORCE_FROM
    _LOG.warning(
        "care.ring.suspect",
        extra={"sender": sender, "facility": facility, "injection": injected, "blocked": enforced},
    )
    return not enforced


async def main(need: Need, city: City) -> None:
    message = city.inbound
    if message is None or not await _admitted(city, message):
        return
    text = message.text or need.summary
    if clinical(text):
        raise OutOfScope()
    if not message.need_id:
        # Every case message has a need_id. Without one, history() reads the whole mailbox (up to
        # 5 signed pages of 200): the conformance probes have none, and that kept the turn open
        # past the 5 s custody.ack waits for the lease renew (same fix as the hospital, PR #74).
        return
    # A relay error here (504 under load) used to leave the brain with an exception: the harness closes the
    # message as rejected for good and the confirm never comes back. Read again, then go on with the message.
    case = [message]
    for attempt in range(3):
        try:
            case = await city.history(need_id=message.need_id)
            break
        except CapError:
            if attempt < 2:
                await asyncio.sleep(1.0 + attempt)
    await handle(role_of(), city, message, case)


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
    if role == "family_counseling":
        await _family(city, message, chat)


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
        return None
    return parsed


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


async def _say(city: City, to: str, text: str) -> bool:
    try:
        await city.say(to, text)
    except CapError:
        return False
    return True


# The Relay can refuse a hold or a commit at once with a CapError. These have no definite outcome: the
# line may or may not be on the Ledger, so it is sent again on the next read (the citizen's or the booking
# centre's repeated confirm, the Ledger's own reply). Any other code is a refusal, answered like the
# Ledger's own ``refused`` line. Before, ``_say`` swallowed both and the confirm stayed without an answer
# (3590002 in the hospital, the consultorio's cancel EXPIRED one second after the confirm).
_UNCERTAIN = {
    "RATE_LIMITED", "DRAINING", "QUARANTINED", "SUSPENDED", "UPSTREAM_TIMEOUT", "AGENT_LOST_CUSTODY",
    "TARGET_NOT_VISIBLE",
}


async def _say_ledger(
    city: City, message: Message, chat: list[Message], text: str, *, op: str, slot: str, hold_id: str = ""
) -> str:
    """Send a hold or a commit. "sent" (or already there: DUPLICATE), "uncertain", or "refused" (handled)."""

    try:
        await city.say(LEDGER, text)
    except CapError as error:
        _LOG.warning("care.%s.failed need=%s slot=%s code=%s", op, (message.need_id or "")[:48], slot, error.code)
        if error.code in {"DUPLICATE", "IDEMPOTENCY_CONFLICT"}:
            return "sent"
        if error.code in _UNCERTAIN:
            return "uncertain"
        line = f"refused {op} slot_id={slot} code={error.code}" + (f" hold_id={hold_id}" if hold_id else "")
        refusal = Message(
            type="chat", sender=LEDGER, recipient=city.agent_id, msg_id=f"relay-{op}-{message.msg_id}",
            need_id=message.need_id, conversation_id=message.conversation_id, body={"text": line},
        )
        rows = chat if any(row.msg_id == message.msg_id for row in chat) else [*chat, message]
        await _on_refused(
            city, refusal, rows, hold_self=True, asker=message.sender if message.sender != LEDGER else ""
        )
        return "refused"
    return "sent"


def _latest(chat: list[Message], head: str, token: str) -> Message | None:
    found: Message | None = None
    for row in chat:
        if row.sender == LEDGER and first_word(row.text) == head and token in row.text.split():
            found = row
    return found


# Console 21/11 07:30-08:50 (a case alone on an idle pod): the Ledger answered 40-130 real seconds after each
# request and the push of its reply opened our next turn 40-90 seconds later (held 08:20:49, commit sent
# 08:22:23; 30 of 36 commits refused STALE_FENCE, every commit sent within 10 s of `held` went through).
# The case history shows a reply as soon as the Relay accepts it, so a turn that has just asked the Ledger
# keeps reading the case for up to _WAIT_SECONDS and goes on the moment the reply is there.
# 21/11 10:06-10:10 UTC: the Ledger took 208-217 s per request (350-500 s at 04:00-05:00), so a 180 s wait
# ended just before the reply and the push brought the old delay back.
_WAIT_SECONDS = 420.0
_WAIT_STEP = 1.0


async def _until(
    city: City,
    need_id: str | None,
    chat: list[Message],
    ready: Callable[[list[Message]], bool],
    *,
    patient: bool = False,
) -> list[Message]:
    """Re-read the case until ``ready`` or the wait ends. The push may never arrive (or come late)."""

    fresh = chat
    started, attempt = monotonic(), 0
    while True:
        try:
            fresh = await city.history(need_id=need_id)
        except CapError:
            fresh = chat
        if ready(fresh):
            return fresh
        attempt += 1
        if patient:
            elapsed = monotonic() - started
            if elapsed >= _WAIT_SECONDS:
                return fresh
            await asyncio.sleep(_WAIT_STEP if elapsed < 30 else 2 * _WAIT_STEP)  # a read is a signed relay call
        else:
            if attempt >= _PULL_TRIES:
                return fresh
            await asyncio.sleep(_PULL_PAUSE)


async def _await_line(
    city: City,
    need_id: str | None,
    chat: list[Message],
    head: str,
    token: str,
    *,
    op: str,
    skip: frozenset[str] = frozenset(),
    patient: bool = False,
) -> tuple[Message, list[Message]] | None:
    """The ledger line for ``token``, or a refusal of ``op`` that was not already in ``chat``.
    Rows in ``skip`` (by msg_id) are ignored: a second hold must wait for ITS held line."""

    known = {row.msg_id for row in chat}
    fresh = chat
    started, attempt = monotonic(), 0
    while True:
        try:
            fresh = await city.history(need_id=need_id)
        except CapError:
            fresh = chat
        hit = _latest([row for row in fresh if row.msg_id not in skip], head, token)
        if hit is not None:
            return hit, fresh
        for row in fresh:
            if row.msg_id in known or row.sender != LEDGER:
                continue
            if first_word(row.text) == "refused" and op in words(row.text):
                return row, fresh
        attempt += 1
        if patient:
            elapsed = monotonic() - started
            if elapsed >= _WAIT_SECONDS:
                return None
            await asyncio.sleep(_WAIT_STEP if elapsed < 30 else 2 * _WAIT_STEP)
        else:
            if attempt >= _PULL_TRIES:
                return None
            await asyncio.sleep(_PULL_PAUSE)


def _has_agenda(chat: list[Message]) -> bool:
    agenda = _ledger(chat, "agenda")
    return _when("" if agenda is None else agenda.get("agenda_now", "")) is not None


def _speaks(doctor_id: str, lang: str) -> bool:
    spec = _DOCTORS.get(doctor_id.rsplit("-", 1)[-1])
    if spec is None:
        return False
    langs = spec[0]
    if lang in langs:
        return True
    return "*" in langs and lang not in {"it", "en"}


_AGENDA_RATE = 60  # one real minute is one agenda hour
_HOLD_MARGIN = timedelta(hours=1)  # hold and commit take real time: a slot this close is gone


def _agenda_add(start: datetime, delta: timedelta) -> datetime:
    """``start`` plus ``delta`` of agenda time; Saturday and Sunday do not exist in the agenda."""
    out = start
    while delta > timedelta(0):
        midnight = (out + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        step = min(delta, midnight - out)
        out, delta = out + step, delta - step
        if out.weekday() >= 5:
            out += timedelta(days=7 - out.weekday())
    return out


def _agenda_now(chat: list[Message], real_now: datetime | None = None) -> datetime | None:
    """The agenda clock now: the Ledger's last agenda_now plus the real time since that reply x60.
    The raw value is hours old by the time the citizen answers (console 21/11: past slots offered
    again after a cancel, then refused with reason=past)."""
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


def _lead(priority: str | None) -> timedelta:
    """B and U windows are short (the deadline counts from the citizen's first message to the GP):
    the soonest slot past the minimum wins. Otherwise slots 30 hours ahead come first."""
    return _min_lead(priority) if priority in ("B", "U") else _LEAD


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


def fitting(
    lines: list[str],
    *,
    now: datetime,
    priority: str | None,
    lang: str,
    gender: str | None = None,
    facility: str | None = None,
    procedure: str | None = None,
) -> list[dict[str, str]]:
    """Slots a citizen can accept: future, free, in the priority window, spoken language."""

    if priority == "U":
        horizon: datetime | None = now.replace(hour=23, minute=59, second=59, microsecond=0)
    elif priority == "P":
        horizon = None
    else:
        horizon = _agenda_horizon(now, _DEADLINE_DAYS.get(priority or "", 14))
    earliest = now + _min_lead(priority)
    chosen: list[tuple[datetime, dict[str, str]]] = []
    for line in lines:
        slot = fields_of(line)
        slot_id = slot.get("slot_id")
        doctor = slot.get("doctor_id")
        # Real Ledger lines carry agenda_date / agenda_day; the local stand-in uses at / day.
        at = _when(slot.get("at", "") or slot.get("agenda_date", ""))
        if not slot_id or not doctor or at is None:
            continue
        if procedure and slot.get("procedure") not in (None, procedure):
            continue
        if facility and slot.get("facility") != facility:
            continue
        free = slot.get("free")
        if free is not None and free.isdigit() and int(free) <= 0:
            continue
        reserve = slot.get("urgent_reserve", "").lower() == "true"
        if reserve and priority != "U":
            continue
        if not earliest < at or (horizon is not None and at >= horizon):
            continue
        spec = _DOCTORS.get(doctor.rsplit("-", 1)[-1])
        # A doctor missing from the hand-written table is not dropped: the registry of the
        # live world may use other ids. Language, days and gender are checked only when known.
        if spec is not None:
            if not _speaks(doctor, lang):
                continue
            day = slot.get("day") or slot.get("agenda_day", "")
            if day and day not in spec[2]:
                continue
            if gender and spec[1] != gender:
                continue
        chosen.append((at, slot))
    chosen.sort(key=lambda item: (now is not None and _ahead(now, item[0]) < _lead(priority), item[0], item[1].get("slot_id", "")))
    return [slot for _, slot in chosen]


# --- consultorio (accesso diretto) -------------------------------------------------------------


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


# Console 21/11 05:00-05:15: the Ledger answered agenda and world 7-9 real minutes after the request and
# our first offer reached the citizen about ten minutes after its message. The agenda clock and the slot
# pages are the same for every case of a wave: a reading made for one case serves the others for five
# minutes (a hold on a slot taken in the meantime is refused and the next offers follow).
_SHARED_SECONDS = 300
_SHARED: dict[tuple[str, str], tuple[Message, datetime]] = {}
_LAST_WAVE: list[str] = [""]  # the wave of the latest shared reading, for searches with no citizen


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


def _shared_reads(chat: list[Message], wave: str, procedure: str, *, first_page: bool = False) -> list[Message]:
    """Remember this case's agenda and slot pages; put before the chat what the other cases of the
    wave read in the last minutes and this case lacks (its own readings come later and win)."""
    now, have = datetime.now(timezone.utc), set()
    for row in chat:
        key = _shared_key(row)
        if key is None:
            continue
        _LAST_WAVE[0] = key[0]
        have.add(key)
        read = _when(row.sent_at or "") or now
        if key not in _SHARED or _SHARED[key][1] <= read:
            _SHARED[key] = (row, read)
    if not wave:
        return chat
    if first_page and any(owner == wave and kind.startswith(procedure + " p") for owner, kind in have):
        return chat  # the case pages forward from its own reading
    wanted = {"agenda", f"{procedure} p1"} if first_page else None
    shared = [
        row for (owner, kind), (row, read) in _SHARED.items()
        if owner == wave and (owner, kind) not in have and now - read <= timedelta(seconds=_SHARED_SECONDS)
        and (kind in wanted if wanted else (kind == "agenda" or kind.startswith(procedure + " p")))
    ]
    return [*shared, *chat] if shared else chat


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
        # One message can carry several offers, one per line (a rebooking sends three).
        for line in row.text.splitlines():
            if first_word(line) != "offer":
                continue
            slot = fields_of(line).get("slot_id")
            if slot:
                found.add(slot)
    return found


def _withdrawn(chat: list[Message], agent: str) -> set[str]:
    """Slots we cancelled. The citizen drops the rest, so those are offered again."""

    by_offer: dict[str, str] = {}
    for row in chat:
        if row.sender != agent:
            continue
        for line in row.text.splitlines():
            if first_word(line) != "offer":
                continue
            fields = fields_of(line)
            offer_id = fields.get("offer_id")
            slot = fields.get("slot_id")
            if offer_id and slot:
                by_offer[offer_id] = slot
    dropped: set[str] = set()
    for row in chat:
        for line in row.text.splitlines():
            if "cancel" not in words(line):
                continue
            slot = by_offer.get(fields_of(line).get("offer_id", ""))
            if slot:
                dropped.add(slot)
    return dropped


def _lang(chat: list[Message]) -> str:
    for row in chat:
        if row.sender.startswith("citizen:"):
            lang = fields_of(row.text).get("lang", "")
            if lang:
                return lang
    return "it"


def _gender(chat: list[Message]) -> str | None:
    for row in chat:
        if not row.sender.startswith("citizen:"):
            continue
        raw = fields_of(row.text).get("gender_preference") or fields_of(row.text).get("gender")
        if raw in {"m", "f"}:
            return raw
    return None


def _offer_line(slot: dict[str, str], number: str | None, priority: str | None) -> str:
    at = slot.get("at") or slot.get("agenda_date", "")
    parts = [
        "offer",
        f"offer_id=of-{slot['slot_id']}",
        f"slot_id={slot['slot_id']}",
        f"doctor_id={slot['doctor_id']}",
        f"facility={slot['facility']}",
        f"procedure={slot['procedure']}",
        f"agenda_date={at}",
        f"agenda_day={slot.get('day') or slot.get('agenda_day', '')}",
        f"expiry={at}",
    ]
    if priority:
        parts.append(f"priority={priority}")
    if number:
        parts.append(f"prescription_number={number}")
    return " ".join(parts)


def _our_offer(chat: list[Message], agent: str, offer_id: str) -> dict[str, str]:
    token = f"offer_id={offer_id}"
    for row in chat:
        if row.sender != agent:
            continue
        # The offer's own line: a message with several offers must not give the first one's slot.
        for line in row.text.splitlines():
            if token in line.split() and "offer" in words(line):
                return fields_of(line)
    return {}


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

    __slots__ = ("offers", "trigger", "again", "reply", "msgs")

    def __init__(self) -> None:
        self.offers: set[str] = set()
        self.trigger = ""
        self.again: set[str] = set()
        # A search's first reply, sent again word for word when the same request_id comes back,
        # and the request messages it was sent for.
        self.reply = ""
        self.msgs: set[str] = set()


# Every Ledger or citizen message opens its own turn, and turns of one need run at the same
# time. Each reads the case before the others' offers are in it, so offers wait on this.
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


# Slots this process knows are not free. Console 21/11 07:30-08:50: five citizens were offered the same four
# slots (the only valid ones on page 1); the first confirm held the first slot, the others got NO_CAPACITY a
# hundred seconds later, and the replacement offers named the refused slot again (2560005, 3290003, 3200003).
# This process holds every slot of its own facility, so it can remember what it learns about a slot.
_GONE_FOR = {"held": 150.0, "full": 150.0, "past": 1e9, "booked": 1e9}  # real seconds
_GONE: dict[str, tuple[float, str, str]] = {}  # slot_id -> (until, why, the case that holds it)
_OFFERED: dict[str, float] = {}  # slot_id -> when it was last offered, to anyone
_SPREAD_SECONDS = 150.0  # about the time a citizen takes to answer and the Ledger to hold


def _mark_gone(slot: str, why: str, owner: str = "") -> None:
    if slot:
        _GONE[slot] = (monotonic() + _GONE_FOR[why], why, owner)


def _release(slot: str, owner: str = "") -> None:
    """The hold lapsed (the Ledger refused the commit): free again, unless booked or past."""

    mark = _GONE.get(slot)
    if mark and mark[1] in {"held", "full"} and mark[2] in {"", owner}:
        del _GONE[slot]


def _gone(besides: str = "") -> set[str]:
    """Slots not free for this case: what other cases hold or booked, and every slot that has passed.
    ``besides`` is the case itself: its own hold is not a reason to refuse its own confirm."""

    now = monotonic()
    for slot in [slot for slot, mark in _GONE.items() if mark[0] <= now]:
        del _GONE[slot]
    return {slot for slot, (_, why, owner) in _GONE.items() if not besides or owner != besides or why == "past"}


_PENDING = "replace:pending"  # in a case's memory: the cancel is out, the replacement offers are not


def _spread(slots: list[dict[str, str]]) -> list[dict[str, str]]:
    """Slots nobody was offered in the last _SPREAD_SECONDS first: citizens take the first offer, so the same
    first slot for all of them is a certain NO_CAPACITY for all but one."""

    now = monotonic()
    fresh = [s for s in slots if now - _OFFERED.get(s.get("slot_id", ""), -1e9) > _SPREAD_SECONDS]
    return fresh + [s for s in slots if s not in fresh]


async def _desk(
    city: City,
    message: Message,
    chat: list[Message],
    *,
    hold_self: bool,
    fixed: str | None,
) -> None:
    # Confirms and check-ins reach _facility first (see _family); the desk only offers slots.
    if message.sender == city.agent_id:
        return
    if message.sender == LEDGER or message.sender.startswith("citizen:"):
        await _advance(city, message, chat, fixed=fixed, replacing=False)


async def _advance(
    city: City,
    message: Message,
    chat: list[Message],
    *,
    fixed: str | None,
    replacing: bool,
    resume: bool = False,
) -> None:
    key = message.need_id or message.msg_id
    gate = _GATES.get(key)
    if gate is None:
        gate = _GATES[key] = _Gate()
    gate.turns += 1
    try:
        async with gate.lock:
            await _advance_alone(city, message, chat, key, fixed=fixed, replacing=replacing, resume=resume)
    finally:
        gate.turns -= 1
        if gate.turns == 0 and _GATES.get(key) is gate:
            del _GATES[key]


async def _advance_alone(
    city: City,
    message: Message,
    chat: list[Message],
    key: str,
    *,
    fixed: str | None,
    replacing: bool,
    resume: bool = False,
) -> None:
    agent = city.agent_id
    citizen = _citizen(chat)
    if citizen is None or not fixed:
        return
    # This turn holds the lock of the case: what the turns before it sent (and what the pod before this one
    # sent, after a release) is in the history now. The state below is read from there, not from the read
    # this turn made before it got the lock.
    chat = await _reread(city, message, chat)
    sent = _sent(key)

    def owing(rows: list[Message]) -> tuple[str, bool]:
        """The cancel the citizen still waits for offers after, and whether this case owes them: a replacement
        not sent yet (the Ledger answered after the wait of the turn that sent the cancel, console 911000381:
        five minutes without offers) is completed by the turn of that answer. The cancel without offers
        after it is in the history too, which a pod that took over (a release) can read: console 003810002,
        the cancel went out from the old pod, the Ledger's page reached the new one."""
        owed = _owed(rows, agent, citizen)
        return owed, _PENDING in sent.offers or bool(owed and f"replaced:{owed}" not in sent.offers)

    if resume and not owing(chat)[1]:
        return  # only finishing the offers a cancel dropped: nothing is owed, a citizen's message gets no more
    # Direct access: no prescription and no waiting list, the procedure is fixed. Ask, then
    # read the reply from history: the push of a ledger message does not open a turn.
    procedure, priority, number = fixed, None, None
    now = world = None
    wave = citizen.removeprefix("citizen:").split("-", 1)[0]
    for _pass in range(3):
        chat = _shared_reads(chat, wave, procedure, first_page=True)
        now = _agenda_now(chat)
        world = _latest_slots(chat)
        if now is not None and world is not None:
            break
        if _pass == 2:
            return
        if now is None and not _exact(chat, agent, "agenda"):
            await _say(city, LEDGER, "agenda")
        if world is None and not _asked(chat, agent, procedure, 1):
            await _say(city, LEDGER, f"world procedure={procedure} page=1")
        chat = await _until(
            city,
            message.need_id,
            chat,
            lambda rows: _has_agenda(rows) and _latest_slots(rows) is not None,
            patient=_pass == 0,
        )
    if now is None or world is None:
        return
    # A cancel drops every offer the citizen was holding, so the ones still free are sent again,
    # once per cancel: a second turn for the same cancel or refusal does not repeat them.
    refused = {item.removeprefix("refused:") for item in sent.offers if item.startswith("refused:")}
    owed, pending = owing(chat)  # the wait above may have shown the offers sent meanwhile
    replacing = replacing or pending
    if resume and not replacing:
        return
    if replacing:
        trigger = fields_of(message.text).get("offer_id") or message.msg_id
        if sent.trigger != trigger:
            sent.trigger = trigger
            sent.again = set()
        taken = _withdrawn(chat, agent) | sent.again
    else:
        taken = _offered(chat, agent) | {
            item for item in sent.offers if not item.startswith(("refused:", "replaced:", _PENDING))
        }
        if taken and message.sender == LEDGER:
            # A Ledger reply (agenda, slots) after our offers: each of them used to add three more.
            return
    # A slot the Ledger refused to this citizen, or that another case holds or booked, is never offered
    # again: the cancel we have just sent is not in ``chat`` yet, so it cannot be read back from there.
    excluded = taken | refused | _gone()
    chosen = [
        slot
        for slot in fitting(
            [line for line in world.splitlines() if "slot_id=" in line],
            now=now,
            priority=priority,
            lang=_lang(chat),
            gender=_gender(chat),
            facility=agent if fixed == "CONS-GIN" else None,
            procedure=procedure,
        )
        if slot.get("slot_id") not in excluded
    ]
    if chosen:
        # Every offer in ONE message: the citizen chooses in the turn of a single message (kit).
        # One message per offer left the citizen confirming the first one 18-34 minutes later,
        # already expired (journeys 256, 1970005).
        picked = _spread(chosen)[:3]
        lines = [_offer_line(slot, number, priority) for slot in picked]
        lines.append("Mi risponda con l'orario che preferisce; se nessuno le va bene, me lo dica e cerco altre date.")
        if await _say(city, citizen, "\n".join(lines)):
            sent.offers.discard(_PENDING)
            if owed:
                sent.offers.add(f"replaced:{owed}")  # the history may not show these offers to the next turn yet
            for slot in picked:
                sent.offers.add(slot["slot_id"])
                _OFFERED[slot["slot_id"]] = monotonic()
                if replacing:
                    sent.again.add(slot["slot_id"])
        return
    if taken and not replacing:
        return
    page, pages = _page(world)
    if page < pages and page < _MAX_PAGE and not _asked(chat, agent, procedure, page + 1):
        await _say(city, LEDGER, f"world procedure={procedure} page={page + 1}")


async def _on_confirm(
    city: City, message: Message, chat: list[Message], *, hold_self: bool
) -> None:
    fields = fields_of(message.text)
    offer_id = fields.get("offer_id", "")
    offer = _our_offer(chat, city.agent_id, offer_id) if offer_id else {}
    slot = fields.get("slot_id") or offer.get("slot_id", "")
    if not slot or not fields.get("consent_ref"):
        return
    # Idempotency (level 7): turns of one confirm run one after the other, and each reads the
    # case again once it holds the lock, so a repeated confirm sees the hold and the receipt.
    async with _SearchLock(message, f"confirm:{message.need_id or message.msg_id}:{slot}"):
        fresh = await _reread(city, message, chat)
        await _confirm_once(city, message, fresh, slot, hold_self=hold_self)


def _our_receipt(chat: list[Message], agent: str, slot: str, to: str) -> Message | None:
    """The receipt we already sent to ``to`` for ``slot``."""

    found: Message | None = None
    for row in chat:
        if (
            row.sender == agent
            and row.recipient == to
            and first_word(row.text) == "booking.receipt"
            and f"slot_id={slot}" in row.text.split()
        ):
            found = row
    return found


def _after(chat: list[Message], message: Message, row: Message) -> bool:
    """True when ``row`` comes after ``message`` in the case history."""

    order = {item.msg_id: index for index, item in enumerate(chat)}
    if message.msg_id not in order or row.msg_id not in order:
        return False
    return order[row.msg_id] > order[message.msg_id]


async def _confirm_once(
    city: City, message: Message, chat: list[Message], slot: str, *, hold_self: bool
) -> None:
    agent = city.agent_id
    fields = fields_of(message.text)
    offer_id = fields.get("offer_id", "")
    consent = fields.get("consent_ref", "")
    offer = _our_offer(chat, agent, offer_id) if offer_id else {}
    memory = _sent(f"confirm:{message.need_id or message.msg_id}")
    # The same confirm again: same receipt, never a second hold. It is sent again word for word,
    # once per repeated confirm, because the first one may not have reached the sender.
    receipt = _our_receipt(chat, agent, slot, message.sender)
    if receipt is not None:
        if f"resent:{message.msg_id}" in memory.offers or _after(chat, message, receipt):
            return
        memory.offers.add(f"resent:{message.msg_id}")
        await _say(city, message.sender, receipt.text)
        return
    # MACH-1.3 R7: compare the agenda with the slot before the hold. A slot already past, or too
    # close to hold and commit, is answered with reason=past and new offers (console 21/11: the
    # citizen confirmed 20 minutes after the offer and the Ledger refused the hold with EXPIRED).
    at = _when(offer.get("agenda_date", "") or offer.get("at", ""))
    wave = message.sender.removeprefix("citizen:").split("-", 1)[0] if message.sender.startswith("citizen:") else _LAST_WAVE[0]
    now = _agenda_now(_shared_reads(chat, wave, "", first_page=True))  # the offer may have used a shared clock
    if at is not None and now is not None and at <= now + _HOLD_MARGIN:
        if not _we(chat, agent, f"slot_id={slot}", to=message.sender, word="cancel"):
            ids = (f"offer_id={offer_id} " if offer_id else "") + f"slot_id={slot}"
            await _say(city, message.sender, f"cancel {ids} reason=past Questo orario è già passato.")
        elif "cancel" in _reacted_since(chat, agent, slot, message):
            # This very confirm was answered already (the pod before was stopped in the middle of it).
            if hold_self and message.sender.startswith("citizen:"):
                await _resume_owed(city, message, chat)
            return
        if hold_self and message.sender.startswith("citizen:"):
            await _replace_offers(city, message, chat)
        return
    # The Ledger already refused this slot to this case, or another case of this process holds or booked
    # it, or it has passed: a hold would only be refused again after a minute or two (NO_CAPACITY 2560005,
    # 3290003 after 100 s) and the citizen repeats the confirm (07:41, 07:57, 08:13) into the silence.
    # Answer now, with the next free slots, and only once per confirm.
    key = message.need_id or message.msg_id
    gone = _gone(besides=key)
    if (
        f"refused:{slot}" in _sent(key).offers
        or _cancelled_for(chat, agent, slot, message.sender)  # a pod that took over knows it from the history
        or slot in gone
    ):
        if f"gone:{message.msg_id}" not in memory.offers:
            memory.offers.add(f"gone:{message.msg_id}")
            if "cancel" in _reacted_since(chat, agent, slot, message):
                # This very confirm was answered already (the pod before was stopped in the middle of it).
                if hold_self and message.sender.startswith("citizen:"):
                    await _resume_owed(city, message, chat)
                return
            code = "EXPIRED" if _GONE.get(slot, (0, "", ""))[1] == "past" else "NO_CAPACITY"
            await _recover(city, message, chat, slot, code, hold_self=hold_self,
                           target=message.sender, offer_id=offer_id)
        return
    citizen = fields.get("citizen") or (
        message.sender if message.sender.startswith("citizen:") else ""
    )
    number = fields.get("prescription_number") or offer.get("prescription_number")
    # The consultorio always books its own slots (no forwarding to another facility).
    hold_consent = consent
    if message.sender.startswith("agent:") and _other_asst(message.sender, agent):
        # Rule P2: a hold in another ASST needs the cross_asst consent first. The booking
        # centre sends it as cross_consent_ref= (team contract; the kit has one consent_ref).
        cross = fields.get("cross_consent_ref") or fields.get("cross_asst_consent_ref", "")
        if cross:
            hold_consent = cross
        elif _rule_on(await _fresh_rules(city, message, chat), "P2"):
            if not _we(chat, agent, f"slot_id={slot}", to=message.sender, word="cancel"):
                parts = ["cancel"]
                if offer_id:
                    parts.append(f"offer_id={offer_id}")
                parts += [f"slot_id={slot}", "reason=consent_missing"]
                await _say(city, message.sender, " ".join(parts))
            return
    # The history may not show a hold we just sent: this process remembers it too.
    if f"hold:{slot}" not in memory.offers and not _we(
        chat, agent, f"slot_id={slot}", to=LEDGER, word="hold"
    ):
        parts = ["hold", f"slot_id={slot}"]
        if citizen:
            parts.append(f"citizen={citizen}")
        if number:
            parts.append(f"prescription_number={number}")
        parts.append(f"consent_ref={hold_consent}")
        memory.offers.add(f"hold:{slot}")
        _mark_gone(slot, "held", key)  # the other cases of this process stop offering it, now
        outcome = await _say_ledger(city, message, chat, " ".join(parts), op="hold", slot=slot)
        if outcome != "sent":
            if outcome == "uncertain":
                _release(slot, key)
                memory.offers.discard(f"hold:{slot}")  # the confirm sent again holds again
            return  # refused: _say_ledger has already answered like a Ledger `refused hold`
    await _finish_booking(city, message, chat, slot, hold_self=hold_self)


# --- facility ----------------------------------------------------------------------------------


def _facility_turn(message: Message, agent: str = "") -> bool:
    head = first_word(message.text)
    kind = words(message.text)
    if _is_fault(message, agent):
        return True
    if message.sender == LEDGER and head in {"held", "committed", "checked_in"}:
        return True
    if message.sender == LEDGER and head == "refused" and kind & {"hold", "commit"}:
        return True
    if "checkin" in kind and message.sender.startswith("citizen:"):
        return True
    return "confirm" in kind and (
        message.sender.startswith("agent:") or message.sender.startswith("citizen:")
    )


async def _family(city: City, message: Message, chat: list[Message]) -> None:
    agent = city.agent_id
    if _is_search(message, agent):
        await _on_search(city, message, chat)
        return
    if _facility_turn(message, agent):
        await _facility(city, message, chat, hold_self=True)
        return
    # A booking was cancelled and the fresh slots are on their way: the rebooking message goes
    # out whole, so the desk must not offer anything on its own in the meantime.
    if message.sender == LEDGER and first_word(message.text) in {"slots", "agenda"}:
        if _open_faults(chat, agent):
            await _resume_faults(city, message, chat)
            return
    # A case opened by another booking centre's search is not a direct-access citizen case:
    # its Ledger replies resume that search and never reach the citizen desk.
    if any(_is_search(row, agent) for row in chat):
        if message.sender == LEDGER:
            await _resume_searches(city, message, chat)
            # The citizen of a case a booking centre searched in too (console 003810002) may be waiting for the
            # offers a cancel of ours dropped: the Ledger's agenda and slots complete them as in any other case.
            if first_word(message.text) in {"slots", "agenda"}:
                await _resume_owed(city, message, chat)
        return
    await _desk(city, message, chat, hold_self=True, fixed="CONS-GIN")


async def _facility(
    city: City,
    message: Message,
    chat: list[Message],
    *,
    hold_self: bool,
) -> None:
    head = first_word(message.text)
    kind = words(message.text)
    if _is_fault(message, city.agent_id):
        await _on_fault(city, message, chat)
    elif message.sender == LEDGER and head == "held":
        await _on_held(city, message, chat)
    elif message.sender == LEDGER and head == "committed":
        await _on_committed(city, message, chat)
    elif message.sender == LEDGER and head == "refused" and kind & {"hold", "commit"}:
        await _on_refused(city, message, chat, hold_self=hold_self)
    elif message.sender == LEDGER and head == "checked_in":
        await _on_checked_in(city, message, chat)
    elif "checkin" in kind and message.sender.startswith("citizen:"):
        await _on_checkin(city, message, chat)
    elif "confirm" in kind:
        await _on_confirm(city, message, chat, hold_self=hold_self)


def _booking_of(chat: list[Message], agent: str, slot_id: str) -> tuple[str, str, str | None]:
    """Who asked us to book this slot, the consent, and the prescription, if we have them."""

    token = f"slot_id={slot_id}"
    sender = ""
    consent = ""
    number: str | None = None
    for row in chat:
        if token not in row.text.split():
            continue
        fields = fields_of(row.text)
        if "confirm" in words(row.text) and row.sender not in (LEDGER, agent):
            sender = row.sender
            consent = fields.get("consent_ref", consent)
            number = fields.get("prescription_number") or number
        if row.sender == agent and "hold" in words(row.text):
            consent = fields.get("consent_ref", consent)
            number = fields.get("prescription_number") or number
            sender = sender or fields.get("citizen", "")
    return sender, consent, number


def _hold_slot(chat: list[Message], agent: str, hold_id: str) -> str:
    token = f"hold_id={hold_id}"
    for row in chat:
        if token in row.text.split() and (row.sender == agent or row.sender == LEDGER):
            slot = fields_of(row.text).get("slot_id", "")
            if slot:
                return slot
    return ""


def _our_commit(chat: list[Message], agent: str, hold_id: str) -> bool:
    """A commit we actually sent. The ledger's held line also contains the word commit."""

    token = f"hold_id={hold_id}"
    for row in chat:
        if row.sender != agent or row.recipient != LEDGER:
            continue
        if row.text.strip().startswith("commit ") and token in row.text.split():
            return True
    return False


def _reacted_since(chat: list[Message], agent: str, slot: str, row: Message) -> set[str]:
    """How we already answered ``row`` (a refusal or a confirm for ``slot``), as the case history shows it:
    ``"hold"`` (a hold of ours for the slot follows it: the retry is on its way) and ``"cancel"`` (so does the
    cancel, or hold_refused, that tells who confirmed). Empty: not answered.

    A pod that takes over (a release) has no memory of what the one before did: console 003290005 (two
    retry holds for one STALE_FENCE) and 003810002 (the second refusal handled by the old pod, answered
    again by the new one: a third hold on a slot the citizen had been told was gone). A refusal that is in no
    history (the Relay's own) is never answered yet."""

    order = {item.msg_id: index for index, item in enumerate(chat)}
    start = order.get(row.msg_id)
    if start is None:
        return set()
    token = f"slot_id={slot}"
    found: set[str] = set()
    for item in chat[start + 1:]:
        if item.sender != agent:
            continue
        for line in item.text.splitlines():
            if token not in line.split():
                continue
            if first_word(line) == "hold" and item.recipient == LEDGER:
                found.add("hold")
            elif first_word(line) in {"cancel", "hold_refused"} and item.recipient != LEDGER:
                found.add("cancel")
    return found


def _cancelled_for(chat: list[Message], agent: str, slot: str, to: str) -> bool:
    """We already told ``to`` the slot is gone (a cancel or hold_refused for it): this case never holds it again.

    This process keeps it in memory too (``refused:``); after a release only the history has it. A missing
    consent or prescription says nothing about the slot: the confirm may come again with them."""

    token = f"slot_id={slot}"
    for row in chat:
        if row.sender != agent or row.recipient != to:
            continue
        for line in row.text.splitlines():
            if first_word(line) in {"cancel", "hold_refused"} and token in line.split():
                if fields_of(line).get("reason") not in {"consent_missing", "prescription_expired"}:
                    return True
    return False


def _owed(chat: list[Message], agent: str, citizen: str) -> str:
    """The cancel of ours the citizen got last, when no offer or receipt of ours follows it (its msg_id): the
    offers it dropped are still owed. Empty when the citizen is not waiting for any.

    This used to live only in the memory of the pod that sent the cancel (``replace:pending``): the Ledger
    answers the agenda and the next page in minutes, a release in between left the citizen without offers.
    A facility's cancel of a booking (booking_id=) is another flow and brings its own offers."""

    owed = ""
    for row in chat:
        if row.sender != agent or row.recipient != citizen:
            continue
        head = first_word(row.text)
        if any(first_word(line) == "offer" for line in row.text.splitlines()) or head == "booking.receipt":
            owed = ""
        elif head == "cancel":
            fields = fields_of(row.text)
            if fields.get("slot_id") and not fields.get("booking_id"):
                owed = row.msg_id
    return owed


def _latest_hold(chat: list[Message], agent: str) -> tuple[str, str | None]:
    consent = ""
    number: str | None = None
    for row in chat:
        if row.sender != agent or not row.text.strip().startswith("hold "):
            continue
        fields = fields_of(row.text)
        consent = fields.get("consent_ref", consent)
        number = fields.get("prescription_number") or number
    return consent, number


async def _finish_booking(
    city: City,
    message: Message,
    chat: list[Message],
    slot: str,
    *,
    hold_self: bool,
    skip: frozenset[str] = frozenset(),
) -> None:
    """Hold is in the mailbox. Read the held line and commit before this turn ends."""

    # Patient: the Ledger answers in 40-130 s and the push of its reply is 40-90 s later still, while a
    # hold lasts about two minutes (STALE_FENCE). Read the case until the reply is there, commit at once.
    found = await _await_line(
        city, message.need_id, chat, "held", f"slot_id={slot}", op="hold", skip=skip, patient=True
    )
    if found is None:
        _LOG.info("care.held.missing", extra={"need_id": (message.need_id or "")[:48]})
        return
    reply, fresh = found
    if first_word(reply.text) == "refused":
        await _on_refused(city, reply, fresh, hold_self=hold_self)
        return
    if not await _on_held(city, reply, fresh):
        return  # no commit on its way (refused, or the Relay is down): nothing to wait for
    hold_id = fields_of(reply.text).get("hold_id", "")
    if not hold_id:
        return
    done = await _await_line(
        city, message.need_id, fresh, "committed", f"booking_id={hold_id}", op="commit", skip=skip,
        patient=True,
    )
    if done is None:
        _LOG.info("care.commit.missing", extra={"need_id": (message.need_id or "")[:48]})
        return
    reply, fresh = done
    if first_word(reply.text) == "committed":
        await _on_committed(city, reply, fresh)
        return
    if first_word(reply.text) == "refused":
        await _on_refused(city, reply, fresh, hold_self=hold_self)


async def _on_held(city: City, message: Message, chat: list[Message]) -> bool:
    """Commit the hold. False when no commit is on its way (nothing to wait for), True otherwise."""

    fields = fields_of(message.text)
    hold_id = fields.get("hold_id", "")
    slot = fields.get("slot_id", "")
    if not hold_id or not slot:
        _LOG.info("care.held.skip", extra={"head": first_word(message.text)[:40]})
        return False
    memory = _sent(f"confirm:{message.need_id or message.msg_id}")
    _mark_gone(slot, "held", message.need_id or message.msg_id)
    if f"commit:{hold_id}" in memory.offers or _our_commit(chat, city.agent_id, hold_id):
        return True
    _, consent, number = _booking_of(chat, city.agent_id, slot)
    if not consent:
        consent, held_number = _latest_hold(chat, city.agent_id)
        number = number or held_number
    need = fields.get("need_id", "")
    if not consent and need.startswith("N-"):
        # The citizen's booking consent is cons-<need_id>-booking. The held line does not
        # echo the real ref, and the hold that carried it may not be in this page of history.
        consent = f"cons-{need}-booking"
    if not consent:
        _LOG.info("care.held.noconsent", extra={"need_id": need[:48]})
        return False
    parts = [
        "commit",
        f"hold_id={hold_id}",
        f"consent_ref={consent}",
        f"fence={fields.get('fence', '1')}",
    ]
    if number:
        parts.append(f"prescription_number={number}")
    memory.offers.add(f"commit:{hold_id}")
    outcome = await _say_ledger(city, message, chat, " ".join(parts), op="commit", slot=slot, hold_id=hold_id)
    if outcome == "uncertain":
        memory.offers.discard(f"commit:{hold_id}")  # the next read of the case commits again
    return outcome == "sent"


async def _on_committed(city: City, message: Message, chat: list[Message]) -> None:
    fields = fields_of(message.text)
    booking_id = fields.get("booking_id", "")
    ledger_ref = fields.get("ledger_ref", "")
    if not booking_id or not ledger_ref:
        return
    # The committed line may name neither the slot nor the hold: find the slot through the
    # hold (booking_id is the hold_id on the Ledger), else our latest hold. Without the slot
    # the receipt would go to the citizen instead of the booking centre that confirmed.
    slot = fields.get("slot_id") or _hold_slot(
        chat, city.agent_id, fields.get("hold_id") or booking_id
    )
    if not slot:
        for row in chat:
            if row.sender == city.agent_id and row.text.strip().startswith("hold "):
                slot = fields_of(row.text).get("slot_id", slot)
    sender, _, _ = _booking_of(chat, city.agent_id, slot) if slot else ("", "", None)
    target = sender or _citizen(chat)
    if not target:
        return
    _mark_gone(slot, "booked", message.need_id or message.msg_id)
    token = f"booking_id={booking_id}"
    if _we(chat, city.agent_id, token, to=target, word="booking.receipt"):
        return
    # The turn that waited for the commit and the push of the same Ledger line can run together.
    memory = _sent(f"confirm:{message.need_id or message.msg_id}")
    if f"receipt:{booking_id}" in memory.offers:
        return
    memory.offers.add(f"receipt:{booking_id}")
    # Only after a successful commit. offer_id and slot_id let the booking centre match the
    # receipt to the confirm it sent (it compares them when present).
    parts = ["booking.receipt", token, f"ledger_ref={ledger_ref}"]
    if slot:
        offer_id = _confirmed_offer(chat, city.agent_id, slot)
        if offer_id:
            parts.append(f"offer_id={offer_id}")
        parts.append(f"slot_id={slot}")
    if not await _say(city, target, " ".join(parts)):
        memory.offers.discard(f"receipt:{booking_id}")


def _confirmed_offer(chat: list[Message], agent: str, slot_id: str) -> str:
    """The offer_id the confirm for this slot named (the booking centre's own id)."""

    token = f"slot_id={slot_id}"
    found = ""
    for row in chat:
        if row.sender in (LEDGER, agent) or token not in row.text.split():
            continue
        if "confirm" in words(row.text):
            found = fields_of(row.text).get("offer_id", found)
    return found


_CODE = re.compile(r"\b[A-Z][A-Z_]{3,}\b")


def _refusal_reason(text: str) -> str:
    """The Ledger's refusal code (NO_CAPACITY, CONSENT_MISSING, ...), else a generic reason."""

    fields = fields_of(text)
    for key in ("code", "reason", "error"):
        if fields.get(key):
            return fields[key]
    match = _CODE.search(text)
    return match.group(0) if match else "facility_cancelled"


# Level 8: the Ledger's own refusal, as the booking centre reads it. These three are a cancel with
# the code in lower case; any other Ledger code is a hold_refused that names it.
_CANCEL_CODES = {"prescription_expired", "consent_missing", "no_capacity"}


def _refusal_line(reason: str, offer_id: str, slot: str, to_centre: bool) -> str:
    ids = f"offer_id={offer_id} slot_id={slot}"
    if not to_centre or reason == "facility_cancelled":
        return f"cancel {ids} reason={reason}"
    if reason.lower() in _CANCEL_CODES:
        return f"cancel {ids} reason={reason.lower()}"
    return f"hold_refused {ids} ledger_code={reason}"


async def _fresh_rules(city: City, message: Message, chat: list[Message]) -> list[Message]:
    """Ask the Ledger for ``rules`` now (they change mid-game) and wait for the new reply."""

    def count(rows: list[Message]) -> int:
        return sum(1 for row in rows if row.sender == LEDGER and first_word(row.text) == "rules")

    known = count(chat)
    if not await _say(city, LEDGER, "rules"):
        return chat
    return await _until(city, message.need_id, chat, lambda rows: count(rows) > known)


async def _on_refused(
    city: City, message: Message, chat: list[Message], *, hold_self: bool, asker: str = ""
) -> None:
    """A refusal of our hold or commit, from the Ledger or (``asker`` = who confirmed) from the Relay."""

    agent = city.agent_id
    slot = fields_of(message.text).get("slot_id", "")
    if not slot:
        hold_id = fields_of(message.text).get("hold_id", "")
        slot = _hold_slot(chat, agent, hold_id) if hold_id else ""
    if not slot:
        for row in chat:
            if row.sender == agent and row.recipient == LEDGER and "hold" in words(row.text):
                slot = fields_of(row.text).get("slot_id", slot)
    if not slot:
        return
    memory = _sent(f"confirm:{message.need_id or message.msg_id}")
    # The turn that waited for this refusal and the push that delivers it run together: once each.
    if f"refusal:{message.msg_id}" in memory.offers:
        return
    memory.offers.add(f"refusal:{message.msg_id}")
    reason = _refusal_reason(message.text)
    code = reason.upper()
    commit = "commit" in words(message.text)
    owner = message.need_id or message.msg_id
    # What the refusal tells every other case of this process (console 21/11: NO_CAPACITY on a slot another
    # citizen held, EXPIRED "slot ... has passed"): it is not free, do not offer it again.
    if commit:
        _release(slot, owner)  # its hold lapsed
    elif code == "NO_CAPACITY":
        _mark_gone(slot, "full")
    elif code == "EXPIRED":
        _mark_gone(slot, "past", owner)
    else:
        _release(slot, owner)
    # Who confirmed: from our hold line, else (a hold the Relay refused is in no history) from the confirm.
    target = _booking_of(chat, agent, slot)[0] or asker or _citizen(chat) or ""
    # Another pod (a release) has no memory of this refusal: its history shows whether we already answered it,
    # with the retry (console 003290005: two retry holds for one STALE_FENCE) or with the cancel (003810002:
    # a third hold for a citizen who had the cancel).
    answered = _reacted_since(chat, agent, slot, message)
    if answered:
        if "cancel" in answered and hold_self and target.startswith("citizen:"):
            # What the pod before left half done, the replacement offers, is finished from the history.
            await _resume_owed(city, message, chat)
        return
    # A commit refused for an old fence or an expired hold (console 256, 229, 248: the Ledger took longer
    # than the lease): the citizen's confirm is still good, so hold and commit once more before cancelling.
    # One retry per slot: this process remembers it, and so does the history (a second hold of ours for the
    # slot is the retry). EXPIRED on a hold is a slot that has passed: another hold cannot work.
    if (code == "STALE_FENCE" or (code == "EXPIRED" and commit)) and f"retry:{slot}" not in memory.offers:
        prior = [
            row for row in chat
            if row.sender == agent and row.recipient == LEDGER and first_word(row.text) == "hold"
            and f"slot_id={slot}" in row.text.split()
        ]
        if len(prior) == 1:
            memory.offers.add(f"retry:{slot}")
            _mark_gone(slot, "held", owner)
            if await _say(city, LEDGER, prior[-1].text):
                known = frozenset(row.msg_id for row in chat)
                await _finish_booking(city, message, chat, slot, hold_self=hold_self, skip=known)
                return
            _release(slot, owner)
    await _recover(city, message, chat, slot, reason, hold_self=hold_self, target=target)


async def _recover(
    city: City,
    message: Message,
    chat: list[Message],
    slot: str,
    code: str,
    *,
    hold_self: bool,
    target: str,
    offer_id: str = "",
) -> None:
    """The slot is gone for this confirm: say so once, remember it, offer the next free slots.

    The cancel we send is not in ``chat`` yet, so the slot is also kept in this case's memory
    (``refused:``): the replacement offers used to name the refused slot again (2560005, 3290003)."""

    agent = city.agent_id
    _sent(message.need_id or message.msg_id).offers.add(f"refused:{slot}")
    if not offer_id:
        offer_id = _confirmed_offer(chat, agent, slot)
    if not offer_id:
        # Our offers are one message with a line per slot: the offer_id of THIS slot is on its own line.
        for row in chat:
            for text in row.text.splitlines():
                if f"slot_id={slot}" in text.split():
                    offer_id = fields_of(text).get("offer_id", offer_id)
    line = _refusal_line(code, offer_id, slot, target.startswith("agent:"))
    if (
        target
        and offer_id
        and not _we(chat, agent, f"offer_id={offer_id}", to=target, word=line.split()[0])
    ):
        await _say(city, target, line)
    # The consultorio offers its next free slots again, but only to its own citizen: a confirm
    # that came from another booking centre goes back to that centre with the cancel above.
    if hold_self and target.startswith("citizen:"):
        await _replace_offers(city, message, chat)


async def _resume_owed(city: City, message: Message, chat: list[Message]) -> None:
    """A message we already answered with a cancel comes again (the pod before was stopped, the Ledger's reply
    comes late): send the offers that cancel dropped if they are still owed, and nothing else. The cancel
    is never repeated and the offers are never sent twice: ``_owed`` reads both from the history."""

    citizen = _citizen(chat)
    if citizen and _owed(chat, city.agent_id, citizen):
        await _advance(city, message, chat, fixed="CONS-GIN", replacing=False, resume=True)


async def _replace_offers(city: City, message: Message, chat: list[Message]) -> None:
    """A cancel dropped the citizen's offers: send the next free slots. Every cancel goes through here.

    Until the offers are really sent the case stays marked ``replace:pending``: the Ledger may answer
    (agenda, the next page of slots) after the wait of this turn, and the turn of that answer then
    completes them. The cancel for a slot that had passed did not mark the case: 000382 and 911000394
    got the page 2 at 10:31 and 10:45 UTC and never an offer."""

    _sent(message.need_id or message.msg_id).offers.add(_PENDING)
    await _advance(city, message, chat, fixed="CONS-GIN", replacing=True)


async def _on_checkin(city: City, message: Message, chat: list[Message]) -> None:
    booking_id = fields_of(message.text).get("booking_id", "")
    citizen = message.sender if message.sender.startswith("citizen:") else _citizen(chat)
    if not booking_id or not citizen:
        return
    token = f"booking_id={booking_id}"
    if not _we(chat, city.agent_id, token, to=LEDGER, word="checkin"):
        if not await _say(city, LEDGER, f"checkin booking_id={booking_id} citizen={citizen}"):
            return
    found = await _await_line(city, message.need_id, chat, "checked_in", token, op="checkin")
    if found is None:
        _LOG.info("care.checkin.missing", extra={"need_id": (message.need_id or "")[:48]})
        return
    reply, fresh = found
    if first_word(reply.text) == "checked_in":
        await _on_checked_in(city, reply, fresh)


async def _on_checked_in(city: City, message: Message, chat: list[Message]) -> None:
    booking_id = fields_of(message.text).get("booking_id", "")
    citizen = _citizen(chat)
    if not booking_id:
        return
    token = f"booking_id={booking_id}"
    if citizen and not _we(chat, city.agent_id, token, to=citizen, word="checkin"):
        line = f"checkin booking_id={booking_id}"
        ledger_ref = fields_of(message.text).get("ledger_ref") or _ledger_ref(chat, booking_id)
        if ledger_ref:
            line += f" ledger_ref={ledger_ref}"
        await _say(city, citizen, line)


def _ledger_ref(chat: list[Message], booking_id: str) -> str:
    token = f"booking_id={booking_id}"
    found = ""
    for row in chat:
        if row.sender == LEDGER and token in row.text.split():
            found = fields_of(row.text).get("ledger_ref", found)
    return found


# --- ricerca dai centri prenotazioni (need.request -> offer / cancel) ----------------------------
#
# Contract with the booking centre (team note, kit 0.9.202):
#   CUP -> struttura   need.request service_type=... procedure=... priority=... request_id=...
#   struttura -> CUP   one message, one line per slot (max 3):
#                      offer offer_id=... slot_id=... doctor_id=... facility=... procedure=...
#                            agenda_date=... agenda_day=... expiry=... request_id=... [priority=...]
#                      or: cancel request_id=... reason=no_slots|reserved_u|wrong_service|...
#   CUP -> struttura   confirm offer_id=... slot_id=... citizen=... consent_ref=...
#                            prescription_number=... [cross_consent_ref=...] [request_id=...]
#   struttura -> CUP   booking.receipt booking_id=... ledger_ref=... offer_id=... slot_id=...
#                      (only after "committed"), or cancel offer_id=... slot_id=... reason=<code>
# No citizen data travels in the search. Every reply names the request_id it answers.

_TRUE = {"1", "true", "on", "yes", "active", "attiva", "in_force"}
_ANSWERED = "answered"


def _team_of(agent_id: str) -> str:
    """The team segment of ``agent:<team>/<slug>``, or "" when the id does not carry it."""

    head = agent_id.removeprefix("agent:")
    return head.split("/", 1)[0] if "/" in head else ""


def _other_asst(sender: str, me: str) -> bool:
    theirs, ours = _team_of(sender), _team_of(me)
    return bool(theirs and ours and theirs != ours)


def _same_agent(a: str, b: str) -> bool:
    if not a or not b:
        return False
    return a == b or a.rsplit("/", 1)[-1] == b.rsplit("/", 1)[-1]


def _rule_on(chat: list[Message], code: str) -> bool:
    """True when the latest ``rules`` reply of the Ledger shows rule ``code`` in force.

    The exact shape of that reply is not in the kit: a ``P2=on`` style token, or the bare
    code on a line that does not say it is off, both count.
    """

    text = ""
    for row in chat:
        if row.sender == LEDGER and first_word(row.text) == "rules":
            text = row.text
    if not text:
        return False
    lowered = code.lower()
    for key, value in fields_of(text).items():
        if key.lower() == lowered or key.lower().startswith(lowered + "_"):
            return value.lower() in _TRUE
    for line in text.splitlines():
        tokens = {token.strip(".,;:()").lower() for token in line.split()}
        if lowered in tokens:
            return not tokens & {"off", "false", "inactive", "0", "no"}
    return False


def _search_fields(message: Message) -> dict[str, str]:
    fields = fields_of(message.text)
    if message.type != "chat":
        for key, value in message.body.items():
            if isinstance(value, str) and value and key not in fields:
                fields[key] = value
    return fields


def _is_search(message: Message, agent: str) -> bool:
    """A booking centre (ours or another ASST's) asking which slots we have."""

    if not message.sender.startswith("agent:") or _same_agent(message.sender, agent):
        return False
    kind = words(message.text)
    if kind & {"confirm", "cancel", "booking.receipt", "offer", "checkin"}:
        return False
    if message.type == "need.request" or "need.request" in kind:
        # A booking centre's search names what it looks for. The city's conformance probes
        # (need.request service=lab summary=visit from an agent that exists only in the suite)
        # name none of it: waiting for the Ledger on them kept the turn open past custody.ack's 5 s.
        fields = _search_fields(message)
        return bool(fields.get("request_id") or fields.get("procedure") or fields.get("service_type"))
    fields = fields_of(message.text)
    return bool(fields.get("request_id") and (fields.get("procedure") or fields.get("service_type")))


def _request_id(message: Message) -> str:
    return _search_fields(message).get("request_id") or message.msg_id


def _open_searches(chat: list[Message], agent: str) -> list[Message]:
    answered: set[str] = set()
    for row in chat:
        if row.sender != agent or row.recipient == LEDGER:
            continue
        if first_word(row.text) in {"offer", "cancel"}:
            rid = fields_of(row.text).get("request_id")
            if rid:
                answered.add(rid)
    pending: list[Message] = []
    seen: set[str] = set()
    for row in chat:
        if not _is_search(row, agent):
            continue
        rid = _request_id(row)
        if rid in answered or rid in seen or _ANSWERED in _sent(f"search:{rid}").offers:
            continue
        seen.add(rid)
        pending.append(row)
    return pending


async def _on_search(city: City, message: Message, chat: list[Message]) -> None:
    async with _SearchLock(message):
        fresh = await _reread(city, message, chat)
        await _answer_search(city, message, message, fresh)


async def _resume_searches(city: City, message: Message, chat: list[Message]) -> None:
    """A Ledger reply (slots, agenda, rules) for a search an earlier turn could not finish."""

    if first_word(message.text) not in {"slots", "agenda", "rules", "world"}:
        return
    if not _open_searches(chat, city.agent_id):
        return
    async with _SearchLock(message):
        fresh = await _reread(city, message, chat)
        for request in _open_searches(fresh, city.agent_id):
            await _answer_search(city, message, request, fresh)


async def _reread(city: City, message: Message, chat: list[Message]) -> list[Message]:
    try:
        fresh = await city.history(need_id=message.need_id)
    except CapError:
        return chat
    known = {row.msg_id for row in fresh}
    return fresh + [row for row in chat if row.msg_id not in known]


class _SearchLock:
    """Serialize the turns of one case, as ``_advance`` does for the desk."""

    def __init__(self, message: Message, key: str = "") -> None:
        self.key = key or "search:" + (message.need_id or message.msg_id)
        self.gate: _Gate | None = None

    async def __aenter__(self) -> None:
        gate = _GATES.get(self.key)
        if gate is None:
            gate = _GATES[self.key] = _Gate()
        gate.turns += 1
        self.gate = gate
        await gate.lock.acquire()

    async def __aexit__(self, *exc: object) -> None:
        gate = self.gate
        if gate is None:
            return
        gate.lock.release()
        gate.turns -= 1
        if gate.turns == 0 and _GATES.get(self.key) is gate:
            del _GATES[self.key]


def _latest_slots_for(chat: list[Message], procedure: str) -> str | None:
    """The newest ``slots`` reply that answers ``procedure`` (or names no procedure at all)."""

    found: str | None = None
    for row in chat:
        if row.sender != LEDGER or first_word(row.text) != "slots":
            continue
        lines = [line for line in row.text.splitlines() if "slot_id=" in line]
        procs = {fields_of(line).get("procedure") for line in lines} - {None}
        if not procs or procedure in procs:
            found = row.text
    return found


def _facility_slots(
    lines: list[str], *, now: datetime | None, priority: str | None, procedure: str, me: str
) -> tuple[list[dict[str, str]], int]:
    """Our own free slots for ``procedure`` inside the priority window.

    Returns the slots and how many were left out only because of the urgent reserve (P3).
    Language and gender are not known in a search without citizen data, so they are not used.
    """

    if now is None:
        horizon = None
        earliest = None
    elif priority == "U":
        horizon = now.replace(hour=23, minute=59, second=59, microsecond=0)
        earliest = now + _min_lead(priority)
    elif priority == "P":
        horizon = None
        earliest = now + _min_lead(priority)
    else:
        horizon = _agenda_horizon(now, _DEADLINE_DAYS.get(priority or "", 14))
        earliest = now + _min_lead(priority)
    chosen: list[tuple[datetime, dict[str, str]]] = []
    reserved = 0
    gone = _gone()  # held, booked or passed according to what this process has seen
    for line in lines:
        slot = fields_of(line)
        slot_id = slot.get("slot_id")
        at = _when(slot.get("at", "") or slot.get("agenda_date", ""))
        if not slot_id or at is None or slot_id in gone:
            continue
        if slot.get("procedure") not in (None, procedure):
            continue
        if slot.get("facility") and not _same_agent(slot["facility"], me):
            continue
        free = slot.get("free")
        if free is not None and free.isdigit() and int(free) <= 0:
            continue
        if earliest is not None and not earliest < at:
            continue
        if horizon is not None and at >= horizon:
            continue
        if slot.get("urgent_reserve", "").lower() == "true" and priority != "U":
            reserved += 1
            continue
        chosen.append((at, slot))
    chosen.sort(key=lambda item: (now is not None and _ahead(now, item[0]) < _lead(priority), item[0], item[1].get("slot_id", "")))
    return [slot for _, slot in chosen], reserved


# Our doctors, from the world registry (asst-bicocca). Sent as doctor_lang / doctor_gender in the
# level-4 common format, so other booking centres can pick the doctor who speaks the language.
_OUR_DOCTORS = {
    "asst-bicocca-h1": ("it/en", "f"), "asst-bicocca-h2": ("it", "m"),
    "asst-bicocca-h3": ("it/ti", "m"), "asst-bicocca-c1": ("it/en", "f"),
}


def _our_doctor(doctor_id: str) -> tuple[str, str] | None:
    return _OUR_DOCTORS.get(doctor_id) or _OUR_DOCTORS.get(f"asst-bicocca-{doctor_id.rsplit('-', 1)[-1]}")


def _partner_offer(slot: dict[str, str], me: str, priority: str | None, request_id: str) -> str:
    at = slot.get("at") or slot.get("agenda_date", "")
    day = slot.get("day") or slot.get("agenda_day", "")
    parts = [
        "offer",
        f"offer_id=of-{slot['slot_id']}",
        f"slot_id={slot['slot_id']}",
    ]
    if slot.get("doctor_id"):
        parts.append(f"doctor_id={slot['doctor_id']}")
    parts += [
        f"facility={slot.get('facility') or me}",
        f"procedure={slot.get('procedure', '')}",
        f"agenda_date={at}",
    ]
    if day:
        parts.append(f"agenda_day={day}")
    if known := _our_doctor(slot.get("doctor_id", "")):
        parts += [f"doctor_lang={known[0]}", f"doctor_gender={known[1]}"]
    parts += [f"expiry={at}", f"request_id={request_id}"]
    if priority:
        parts.append(f"priority={priority}")
    return " ".join(part for part in parts if not part.endswith("="))


def _replies_to(chat: list[Message], agent: str, centre: str, rid: str) -> list[Message]:
    """Our replies (offer or cancel) to ``centre`` for the search ``rid``, oldest first."""

    token = f"request_id={rid}"
    return [
        row
        for row in chat
        if row.sender == agent
        and row.recipient == centre
        and first_word(row.text) in {"offer", "cancel"}
        and token in row.text.splitlines()[0].split()
    ]


def _earlier_reply(chat: list[Message], agent: str, centre: str, rid: str) -> str:
    found = _replies_to(chat, agent, centre, rid)
    return found[0].text if found else ""


def _answered_since(
    chat: list[Message], agent: str, centre: str, rid: str, request: Message
) -> bool:
    """True when one of our replies for ``rid`` comes after ``request`` in the history."""

    return any(_after(chat, request, row) for row in _replies_to(chat, agent, centre, rid))


async def _answer_search(
    city: City, trigger: Message, request: Message, chat: list[Message]
) -> None:
    agent = city.agent_id
    fields = _search_fields(request)
    rid = _request_id(request)
    centre = request.sender
    done = _sent(f"search:{rid}")
    # Idempotency (level 7): the same request_id again gets the same offers, word for word, even
    # if the Ledger has changed since. A request that already has its answer gets nothing more.
    earlier = done.reply or _earlier_reply(chat, agent, centre, rid)
    if earlier:
        if request.msg_id in done.msgs or _answered_since(chat, agent, centre, rid, request):
            return
        done.msgs.add(request.msg_id)
        await _say(city, centre, earlier)
        return
    if _ANSWERED in done.offers:
        return

    async def reply(text: str) -> None:
        if await _say(city, centre, text):
            done.offers.add(_ANSWERED)
            done.reply = text
            done.msgs.add(request.msg_id)

    family = role_of()
    service = fields.get("service_type", "")
    if service and family and service.split(".", 1)[0] != family:
        await reply(f"cancel request_id={rid} reason=wrong_service service_type={service}")
        return
    procedure = fields.get("procedure") or ("CONS-GIN" if family == "family_counseling" else "")
    if not procedure:
        await reply(f"cancel request_id={rid} reason=procedure_missing")
        return
    priority = (fields.get("priority") or "").upper() or None

    chat = _shared_reads(chat, _LAST_WAVE[0], procedure)  # MACH-1.3 wants the answer within 10 s
    world = _latest_slots_for(chat, procedure)
    now = _agenda_now(chat)
    if world is None or now is None:
        if world is None and not _asked(chat, agent, procedure, 1):
            await _say(city, LEDGER, f"world procedure={procedure} page=1")
        if now is None and not _exact(chat, agent, "agenda"):
            await _say(city, LEDGER, "agenda")
        if not _exact(chat, agent, "rules"):
            await _say(city, LEDGER, "rules")
        chat = await _until(
            city,
            request.need_id,
            chat,
            lambda rows: _latest_slots_for(rows, procedure) is not None and _has_agenda(rows),
        )
        world = _latest_slots_for(chat, procedure)
        now = _agenda_now(chat)
        if world is None or now is None:
            # The Ledger answers in a later turn; _resume_searches picks the search up there.
            return

    # All pages read so far, so the relaxed alternatives see every slot of the case.
    slots, _ = _facility_slots(
        _all_slot_lines(chat, procedure), now=now, priority=priority, procedure=procedure, me=agent
    )
    criteria = _criteria(fields)
    judged = [(slot, _violations(slot, criteria)) for slot in slots]
    valid = [slot for slot, broken in judged if not broken]
    if valid:
        picked = _spread(valid)[:3]
        await reply("\n".join(_partner_offer(slot, agent, priority, rid) for slot in picked))
        for slot in picked:
            _OFFERED[slot["slot_id"]] = monotonic()
        return
    page, pages = _page(world)
    if page < pages and page < _MAX_PAGE:
        if not _asked(chat, agent, procedure, page + 1):
            await _say(city, LEDGER, f"world procedure={procedure} page={page + 1}")
        return
    # MACH-1.2, empty answer set: the cancel, then at most three offers that each break exactly
    # one relaxable criterion, all in one message.
    lines = [f"cancel reason=no_availability request_id={rid} procedure={procedure}"]
    lines += [
        f"{_partner_offer(slot, agent, priority, rid)} relaxed={broken[0]}"
        for slot, broken in judged
        if len(broken) == 1 and broken[0] in _RELAXABLE
    ][:3]
    await reply("\n".join(lines))


# --- MACH-1.2: criteri estesi ------------------------------------------------------------------
# need.request may carry lang=, gender_preference=m|f, days=tue/thu, after=HH:MM, before=HH:MM
# (local time of the slot, after <= time < before) and wheelchair=true. Language and
# accessibility are never relaxed: a doctor who does not speak the language is no alternative.

# Registry: the consultorio is not wheelchair accessible.
_ACCESSIBLE = False
_RELAXABLE = ("days", "after", "before", "gender_preference")
_DAYS = {
    "mon": "mon", "tue": "tue", "wed": "wed", "thu": "thu", "fri": "fri", "sat": "sat",
    "sun": "sun", "lun": "mon", "mar": "tue", "mer": "wed", "gio": "thu", "ven": "fri",
    "sab": "sat", "dom": "sun",
}
_WEEKDAY = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
# after/before are Milan wall-clock time, the Ledger's agenda_date is UTC. The event runs in
# November (CET, UTC+1); a fixed offset avoids depending on tzdata in the image.
_MILANO = timezone(timedelta(hours=1))


def _clock(value: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?", value.strip())
    if not match or int(match.group(1)) > 23 or int(match.group(2) or 0) > 59:
        return None
    return int(match.group(1)), int(match.group(2) or 0)


def _criteria(fields: dict[str, str]) -> dict:
    raw_days = re.split(r"[/,;\s]+", fields.get("days", "").strip("[]").lower())
    gender = (fields.get("gender_preference") or fields.get("gender") or "").lower()[:1]
    return {
        "lang": fields.get("lang", "").lower().strip(),
        "gender": gender if gender in {"m", "f"} else "",
        "days": {_DAYS[token[:3]] for token in raw_days if token[:3] in _DAYS},
        "after": _clock(fields.get("after", "")),
        "before": _clock(fields.get("before", "")),
        "wheelchair": fields.get("wheelchair", "").lower() in _TRUE,
        # MACH-1.3: the asker's window with date and time (after= with a date is the start too).
        "earliest": _stamp(fields.get("earliest", "") or fields.get("after", "")),
        "deadline": _stamp(fields.get("deadline", "")),
    }


def _stamp(value: str) -> datetime | None:
    return _when(value) if "T" in value else None


def _all_slot_lines(chat: list[Message], procedure: str) -> list[str]:
    """Every slot line the Ledger returned for ``procedure`` in this case (all pages)."""

    seen: dict[str, str] = {}
    for row in chat:
        if row.sender != LEDGER or first_word(row.text) != "slots":
            continue
        for line in row.text.splitlines():
            slot = fields_of(line)
            if slot.get("slot_id") and slot.get("procedure") in (None, procedure):
                seen[slot["slot_id"]] = line
    return list(seen.values())


def _violations(slot: dict[str, str], criteria: dict) -> list[str]:
    """The request criteria this slot breaks (empty: it fits them all)."""

    broken: list[str] = []
    known = _our_doctor(slot.get("doctor_id", ""))
    lang = criteria["lang"]
    if lang and not (known and lang in known[0].split("/")) and not (known is None and lang == "it"):
        broken.append("lang")
    if criteria["gender"] and (known is None or known[1] != criteria["gender"]):
        broken.append("gender_preference")
    at = _when(slot.get("agenda_date", "") or slot.get("at", ""))
    if at is not None and criteria.get("deadline") is not None and at > criteria["deadline"]:
        broken.append("deadline")  # never relaxed: an offer past the deadline is refused
    if at is not None and criteria.get("earliest") is not None and at < criteria["earliest"]:
        broken.append("earliest")
    if at is not None:
        at = at.astimezone(_MILANO)
        day = (slot.get("agenda_day") or slot.get("day") or _WEEKDAY[at.weekday()]).lower()[:3]
        if criteria["days"] and day not in criteria["days"]:
            broken.append("days")
        clock = (at.hour, at.minute)
        if criteria["after"] is not None and clock < criteria["after"]:
            broken.append("after")
        if criteria["before"] is not None and not clock < criteria["before"]:
            broken.append("before")
    if criteria["wheelchair"] and not _ACCESSIBLE:
        broken.append("wheelchair")
    return broken


# --- level 6: rebooking after a cancelled booking ----------------------------------------------
# The Ledger or the city cancels a booking of ours (``fault.cancel``, reason facility_cancelled).
# Whoever booked (the citizen, or the booking centre that confirmed) gets ONE message: the line
# ``cancel reason=facility_cancelled booking_id=...`` and under it up to three replacement offers,
# the same doctor first. The cancelled slot is never offered again. The shape of the fault
# message is not in the kit (team/LIVELLI.md): it is read loosely, from the Ledger or the city only.

_FAULT_WORDS = {"fault.cancel", "booking.cancelled", "cancelled"}


def _is_fault(message: Message, agent: str) -> bool:
    if message.sender == agent or message.sender.startswith("citizen:"):
        return False
    if message.sender != LEDGER and not message.sender.startswith("city:"):
        return False
    if message.type == "fault.cancel" or words(message.text) & _FAULT_WORDS:
        return True
    fields = _search_fields(message)
    return fields.get("reason") == "facility_cancelled" and bool(fields.get("booking_id"))


def _fault_booking(message: Message) -> str:
    fields = _search_fields(message)
    return fields.get("booking_id") or fields.get("hold_id", "")


def _booking_slot(chat: list[Message], agent: str, booking: str, fields: dict[str, str]) -> str:
    """The slot of a booking: the fault line, our receipt, the Ledger's committed line, the hold."""

    if fields.get("slot_id"):
        return fields["slot_id"]
    token = f"booking_id={booking}"
    for row in chat:
        if row.sender == agent and first_word(row.text) == "booking.receipt":
            if token in row.text.split() and fields_of(row.text).get("slot_id"):
                return fields_of(row.text)["slot_id"]
    for row in chat:
        if row.sender == LEDGER and first_word(row.text) == "committed":
            if token in row.text.split():
                line = fields_of(row.text)
                slot = line.get("slot_id") or _hold_slot(chat, agent, line.get("hold_id") or booking)
                if slot:
                    return slot
    return _hold_slot(chat, agent, booking)


def _booking_target(
    chat: list[Message], agent: str, booking: str, slot: str, fields: dict[str, str]
) -> str:
    """Who booked: the receipt's recipient, else who confirmed the slot, else the citizen."""

    token = f"booking_id={booking}"
    for row in chat:
        if row.sender == agent and first_word(row.text) == "booking.receipt":
            if token in row.text.split():
                return row.recipient
    sender = _booking_of(chat, agent, slot)[0] if slot else ""
    return sender or fields.get("citizen", "") or (_citizen(chat) or "")


def _offer_of_slot(chat: list[Message], agent: str, slot: str) -> dict[str, str]:
    """Our own offer line for ``slot``: doctor, priority, request_id and offer_id of the booking."""

    token = f"slot_id={slot}"
    for row in chat:
        if row.sender != agent:
            continue
        for line in row.text.splitlines():
            if first_word(line) == "offer" and token in line.split():
                return fields_of(line)
    return {}


def _index_of(chat: list[Message], message: Message) -> int:
    for index, row in enumerate(chat):
        if row.msg_id == message.msg_id:
            return index
    return len(chat) - 1


def _fault_open(chat: list[Message], agent: str, booking: str) -> bool:
    if _ANSWERED in _sent(f"fault:{booking}").offers:
        return False
    token = f"booking_id={booking}"
    return not any(
        row.sender == agent
        and first_word(row.text) == "cancel"
        and "reason=facility_cancelled" in row.text.splitlines()[0].split()
        and token in row.text.split()
        for row in chat
    )


def _open_faults(chat: list[Message], agent: str) -> list[Message]:
    found: list[Message] = []
    seen: set[str] = set()
    for row in chat:
        if not _is_fault(row, agent):
            continue
        booking = _fault_booking(row)
        if booking and booking not in seen and _fault_open(chat, agent, booking):
            seen.add(booking)
            found.append(row)
    return found


async def _on_fault(city: City, message: Message, chat: list[Message]) -> None:
    if not _fault_booking(message):
        return
    async with _SearchLock(message):
        fresh = await _reread(city, message, chat)
        await _rebook(city, message, fresh)


async def _resume_faults(city: City, message: Message, chat: list[Message]) -> None:
    """A Ledger reply (slots, agenda) for a cancelled booking an earlier turn could not finish."""

    async with _SearchLock(message):
        fresh = await _reread(city, message, chat)
        for fault in _open_faults(fresh, city.agent_id):
            await _rebook(city, fault, fresh)


def _fresh_world(
    chat: list[Message], fault: Message, procedure: str
) -> tuple[list[str], tuple[int, int], datetime | None]:
    """Slot lines, last page and agenda_now the Ledger sent after the cancel."""

    seen: dict[str, str] = {}
    page = (1, 1)
    now: datetime | None = None
    for row in chat[_index_of(chat, fault) + 1 :]:
        if row.sender != LEDGER:
            continue
        head = first_word(row.text)
        if head == "agenda":
            now = _when(fields_of(row.text).get("agenda_now", "")) or now
        elif head == "slots":
            for line in row.text.splitlines():
                slot = fields_of(line)
                if slot.get("slot_id") and slot.get("procedure") in (None, procedure):
                    seen[slot["slot_id"]] = line
            page = _page(row.text)
    return list(seen.values()), page, now


def _asked_since(chat: list[Message], agent: str, fault: Message, text: str) -> bool:
    return any(
        row.sender == agent and row.recipient == LEDGER and row.text.strip() == text
        for row in chat[_index_of(chat, fault) + 1 :]
    )


async def _rebook(city: City, fault: Message, chat: list[Message]) -> None:
    agent = city.agent_id
    fields = _search_fields(fault)
    booking = _fault_booking(fault)
    if not booking or not _fault_open(chat, agent, booking):
        return
    done = _sent(f"fault:{booking}")
    slot = _booking_slot(chat, agent, booking, fields)
    target = _booking_target(chat, agent, booking, slot, fields)
    if not slot or not target:
        _LOG.info("care.rebook.unknown", extra={"need_id": (fault.need_id or "")[:48]})
        done.offers.add(_ANSWERED)
        return
    procedure = fields.get("procedure") or "CONS-GIN"
    ask_world = f"world procedure={procedure} page=1"
    lines, page, now = _fresh_world(chat, fault, procedure)
    if not lines or now is None:
        if not lines and not _asked_since(chat, agent, fault, ask_world):
            await _say(city, LEDGER, ask_world)
        if now is None and not _asked_since(chat, agent, fault, "agenda"):
            await _say(city, LEDGER, "agenda")
        chat = await _until(
            city,
            fault.need_id,
            chat,
            lambda rows: bool(_fresh_world(rows, fault, procedure)[0])
            and _fresh_world(rows, fault, procedure)[2] is not None,
        )
        lines, page, now = _fresh_world(chat, fault, procedure)
        if not lines or now is None:
            return  # the Ledger answers in a later turn: _resume_faults picks it up there
    shown = _offer_of_slot(chat, agent, slot)
    request_id = shown.get("request_id", "")
    priority = (shown.get("priority") or fields.get("priority") or "").upper() or None
    for_citizen = target.startswith("citizen:")
    if for_citizen:
        found = fitting(
            lines, now=now, priority=priority, lang=_lang(chat), gender=_gender(chat),
            facility=agent, procedure=procedure,
        )
    else:
        slots, _ = _facility_slots(lines, now=now, priority=priority, procedure=procedure, me=agent)
        criteria = _criteria({})
        for row in chat:
            if _is_search(row, agent) and request_id and _request_id(row) == request_id:
                criteria = _criteria(_search_fields(row))
        found = [item for item in slots if not _violations(item, criteria)]
    found = [item for item in found if item["slot_id"] != slot]
    doctor = shown.get("doctor_id") or fields.get("doctor_id", "")
    if not doctor:
        ours = next((line for line in lines if f"slot_id={slot}" in line.split()), "")
        doctor = fields_of(ours).get("doctor_id", "")
    # Same doctor first; inside each group the soonest slot first (the lists are already sorted).
    found.sort(key=lambda item: item.get("doctor_id") != doctor)
    if len(found) < 3 and page[0] < page[1] and page[0] < _MAX_PAGE:
        ask_next = f"world procedure={procedure} page={page[0] + 1}"
        if not _asked_since(chat, agent, fault, ask_next):
            await _say(city, LEDGER, ask_next)
            return
    head = f"cancel reason=facility_cancelled booking_id={booking}"
    offer_id = shown.get("offer_id") or _confirmed_offer(chat, agent, slot)
    if offer_id:
        head += f" offer_id={offer_id}"
    head += f" slot_id={slot}"
    if for_citizen:
        number = shown.get("prescription_number")
        offers = [_offer_line(item, number, priority) for item in found[:3]]
    else:
        offers = [_partner_offer(item, agent, priority, request_id) for item in found[:3]]
    if await _say(city, target, "\n".join([head, *offers])):
        done.offers.add(_ANSWERED)
        if for_citizen:
            _sent(fault.need_id or fault.msg_id).offers.update(item["slot_id"] for item in found[:3])
