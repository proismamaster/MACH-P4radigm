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
# Four agenda hours is about half a minute of real time at 480x, so a slot is still
# ahead when the citizen decides. One hour was already past by then.
_LEAD = timedelta(hours=4)
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
    case = await city.history(need_id=message.need_id)
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


def _latest(chat: list[Message], head: str, token: str) -> Message | None:
    found: Message | None = None
    for row in chat:
        if row.sender == LEDGER and first_word(row.text) == head and token in row.text.split():
            found = row
    return found


async def _until(
    city: City,
    need_id: str | None,
    chat: list[Message],
    ready: Callable[[list[Message]], bool],
) -> list[Message]:
    """Re-read the case until ``ready`` or the short wait ends. The push may never arrive."""

    fresh = chat
    for attempt in range(_PULL_TRIES):
        try:
            fresh = await city.history(need_id=need_id)
        except CapError:
            fresh = chat
        if ready(fresh):
            return fresh
        if attempt + 1 < _PULL_TRIES:
            await asyncio.sleep(_PULL_PAUSE)
    return fresh


async def _await_line(
    city: City,
    need_id: str | None,
    chat: list[Message],
    head: str,
    token: str,
    *,
    op: str,
) -> tuple[Message, list[Message]] | None:
    """The ledger line for ``token``, or a refusal of ``op`` that was not already in ``chat``."""

    known = {row.msg_id for row in chat}
    fresh = chat
    for attempt in range(_PULL_TRIES):
        try:
            fresh = await city.history(need_id=need_id)
        except CapError:
            fresh = chat
        hit = _latest(fresh, head, token)
        if hit is not None:
            return hit, fresh
        for row in fresh:
            if row.msg_id in known or row.sender != LEDGER:
                continue
            if first_word(row.text) == "refused" and op in words(row.text):
                return row, fresh
        if attempt + 1 < _PULL_TRIES:
            await asyncio.sleep(_PULL_PAUSE)
    return None


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
        horizon = now + timedelta(days=_DEADLINE_DAYS.get(priority or "", 14))
    earliest = now + _LEAD
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
    chosen.sort(key=lambda item: (item[0], item[1].get("slot_id", "")))
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
) -> None:
    key = message.need_id or message.msg_id
    gate = _GATES.get(key)
    if gate is None:
        gate = _GATES[key] = _Gate()
    gate.turns += 1
    try:
        async with gate.lock:
            await _advance_alone(city, message, chat, key, fixed=fixed, replacing=replacing)
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
) -> None:
    agent = city.agent_id
    citizen = _citizen(chat)
    if citizen is None or not fixed:
        return
    # Direct access: no prescription and no waiting list, the procedure is fixed. Ask, then
    # read the reply from history: the push of a ledger message does not open a turn.
    procedure, priority, number = fixed, None, None
    now = world = None
    for _pass in range(3):
        agenda = _ledger(chat, "agenda")
        now = _when("" if agenda is None else agenda.get("agenda_now", ""))
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
        )
    if now is None or world is None:
        return
    # A cancel drops every offer the citizen was holding, so the ones still free are sent again,
    # once per cancel: a second turn for the same cancel or refusal does not repeat them.
    sent = _sent(key)
    if replacing:
        trigger = fields_of(message.text).get("offer_id") or message.msg_id
        if sent.trigger != trigger:
            sent.trigger = trigger
            sent.again = set()
        taken = _withdrawn(chat, agent) | sent.again
    else:
        taken = _offered(chat, agent) | sent.offers
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
        if slot.get("slot_id") not in taken
    ]
    if chosen:
        for slot in chosen[:3]:
            if await _say(city, citizen, _offer_line(slot, number, priority)):
                sent.offers.add(slot["slot_id"])
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
        if not await _say(city, LEDGER, " ".join(parts)):
            return
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
    city: City, message: Message, chat: list[Message], slot: str, *, hold_self: bool
) -> None:
    """Hold is in the mailbox. Read the held line and commit before this turn ends."""

    found = await _await_line(city, message.need_id, chat, "held", f"slot_id={slot}", op="hold")
    if found is None:
        _LOG.info("care.held.missing", extra={"need_id": (message.need_id or "")[:48]})
        return
    reply, fresh = found
    if first_word(reply.text) == "refused":
        await _on_refused(city, reply, fresh, hold_self=hold_self)
        return
    await _on_held(city, reply, fresh)
    hold_id = fields_of(reply.text).get("hold_id", "")
    if not hold_id:
        return
    done = await _await_line(
        city, message.need_id, fresh, "committed", f"booking_id={hold_id}", op="commit"
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


async def _on_held(city: City, message: Message, chat: list[Message]) -> None:
    fields = fields_of(message.text)
    hold_id = fields.get("hold_id", "")
    slot = fields.get("slot_id", "")
    if not hold_id or not slot:
        _LOG.info("care.held.skip", extra={"head": first_word(message.text)[:40]})
        return
    memory = _sent(f"confirm:{message.need_id or message.msg_id}")
    if f"commit:{hold_id}" in memory.offers or _our_commit(chat, city.agent_id, hold_id):
        return
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
        return
    parts = [
        "commit",
        f"hold_id={hold_id}",
        f"consent_ref={consent}",
        f"fence={fields.get('fence', '1')}",
    ]
    if number:
        parts.append(f"prescription_number={number}")
    memory.offers.add(f"commit:{hold_id}")
    await _say(city, LEDGER, " ".join(parts))


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
    token = f"booking_id={booking_id}"
    if _we(chat, city.agent_id, token, to=target, word="booking.receipt"):
        return
    # Only after a successful commit. offer_id and slot_id let the booking centre match the
    # receipt to the confirm it sent (it compares them when present).
    parts = ["booking.receipt", token, f"ledger_ref={ledger_ref}"]
    if slot:
        offer_id = _confirmed_offer(chat, city.agent_id, slot)
        if offer_id:
            parts.append(f"offer_id={offer_id}")
        parts.append(f"slot_id={slot}")
    await _say(city, target, " ".join(parts))


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
    city: City, message: Message, chat: list[Message], *, hold_self: bool
) -> None:
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
    target, _, _ = _booking_of(chat, agent, slot)
    offer_id = _confirmed_offer(chat, agent, slot)
    if not offer_id:
        for row in chat:
            if f"slot_id={slot}" in row.text.split():
                offer_id = fields_of(row.text).get("offer_id", offer_id)
    line = _refusal_line(_refusal_reason(message.text), offer_id, slot, target.startswith("agent:"))
    if (
        target
        and offer_id
        and not _we(chat, agent, f"offer_id={offer_id}", to=target, word=line.split()[0])
    ):
        await _say(city, target, line)
    # The consultorio offers its next free slots again, but only to its own citizen: a confirm
    # that came from another booking centre goes back to that centre with the cancel above.
    if hold_self and target.startswith("citizen:"):
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
        return True
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
        earliest = now + _LEAD
    elif priority == "P":
        horizon = None
        earliest = now + _LEAD
    else:
        horizon = now + timedelta(days=_DEADLINE_DAYS.get(priority or "", 14))
        earliest = now + _LEAD
    chosen: list[tuple[datetime, dict[str, str]]] = []
    reserved = 0
    for line in lines:
        slot = fields_of(line)
        slot_id = slot.get("slot_id")
        at = _when(slot.get("at", "") or slot.get("agenda_date", ""))
        if not slot_id or at is None:
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
    chosen.sort(key=lambda item: (item[0], item[1].get("slot_id", "")))
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

    world = _latest_slots_for(chat, procedure)
    agenda = _ledger(chat, "agenda")
    now = _when("" if agenda is None else agenda.get("agenda_now", ""))
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
        agenda = _ledger(chat, "agenda")
        now = _when("" if agenda is None else agenda.get("agenda_now", ""))
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
        offers = [_partner_offer(slot, agent, priority, rid) for slot in valid[:3]]
        await reply("\n".join(offers))
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
    }


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
