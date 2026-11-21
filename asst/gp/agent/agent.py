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
from datetime import datetime, timedelta
from hashlib import sha256
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
_PROTOCOLS: dict[str, tuple[str, str]] = {
    "SYM-BACK": ("VIS-FIS", "B"),
    "SYM-KNEE": ("VIS-FIS", "D"),
    "SYM-PALPITATIONS": ("VIS-CARD", "B"),
    "SYM-FOLLOWUP": ("VIS-CARD", "P"),
}
_RED_FLAGS = (
    "perdita di forza alle gambe",
    "loss of strength in the legs",
    "dolore al petto",
    "chest pain",
    # Level 8 hides the red flag in free text: the same two protocol flags, written differently.
    "dolori al petto", "dolore toracico", "male al petto", "fitta al petto", "oppressione al petto",
    "pain in my chest", "chest hurts", "chest pains", "chest tightness",
    "forza alle gambe", "forza nelle gambe", "debolezza alle gambe", "debolezza nelle gambe",
    "gambe deboli", "non sento le gambe", "non sento più le gambe",
    "strength in my legs", "weakness in my legs", "legs are weak", "legs feel weak", "legs gave out",
)
_DEADLINE_DAYS = {"B": 2, "D": 5}
_GP_FIELD = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
_GP_PRIORITIES = frozenset({"U", "B", "D", "P"})
_GP_CLARIFICATION = (
    "Grazie per avermi scritto, la aiuto volentieri. Per prepararle la ricetta giusta, "
    "mi descrive in poche parole il disturbo (dove lo sente e da quanto tempo)?"
)
# Free text -> protocol symptom code. Only a lookup into the protocol table: no diagnosis.
_GP_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("SYM-FOLLOWUP", ("controllo del cuore", "visita di controllo", "follow-up", "follow up",
                      "routine heart check", "heart check-up", "heart checkup")),
    ("SYM-PALPITATIONS", ("palpitazion", "batticuore", "cuore che batte", "cuore batte",
                          "tachicardi", "palpitation", "heart racing", "racing heart")),
    ("SYM-KNEE", ("ginocchio", "ginocchia", "knee")),
    ("SYM-BACK", ("mal di schiena", "dolore alla schiena", "schiena", "lombar", "back pain",
                  "lower back", "backache")),
)
_LOG = logging.getLogger("care")
# The Relay accepts a ledger reply and then the agent rejects the push, so the reply sits in
# the case history and never opens a turn. Wait briefly and read it back from history.
_PULL_TRIES = 24
_PULL_PAUSE = 0.25
# Needs whose sent offers this process remembers; the oldest is forgotten first.
_SENT_NEEDS = 4096
_GP_OUTBOX: OrderedDict[str, deque[Message]] = OrderedDict()


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
    role = role_of()
    urgent = role == "gp" and message.sender.startswith("citizen:") and (
        need.is_emergency or _emergency(message)
    )
    if not urgent and message.sender != LEDGER and clinical(message.text or need.summary):
        raise OutOfScope()
    if role == "gp":
        if not message.need_id:
            if urgent:
                await _say(city, message.sender, "escalate.emergency reason=red_flag")
            return
        async with _case_lock(message.need_id):
            chat = await _turn_history(city, message.need_id)
            if chat is None:
                # The case could not be read (5xx twice). An exception here ends the turn as "agent
                # crashed": the harness acks the message as rejected and it never comes back. A red
                # flag still gets its escalation; a prescription waits for a turn that can read the
                # case (the citizen sends the same content again), never one made blind.
                if urgent:
                    await _gp(city, message, [message], urgent=True)
                return
            if urgent:
                await _gp(city, message, chat, urgent=True)
            else:
                await handle(role, city, message, chat)
        return
    case = await _turn_history(city, message.need_id)
    await handle(role, city, message, case if case is not None else [message])


async def _turn_history(city: City, need_id: str | None) -> list[Message] | None:
    """The case at the start of the turn: one more try on a 5xx (504 under load), else None."""
    for attempt in range(3):
        try:
            return await city.history(need_id=need_id)
        except CapError as error:
            try:
                retry = 500 <= error.http_status() < 600
            except CapError:
                retry = False
            _LOG.warning("gp.history.failed need=%s code=%s attempt=%d", (need_id or "")[:48], error.code, attempt)
            if not retry:
                return None
            await asyncio.sleep(_PULL_PAUSE)
    return None


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
    if role == "gp":
        await _gp(city, message, chat)


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


async def _until(
    city: City,
    need_id: str | None,
    chat: list[Message],
    ready: Callable[[list[Message]], bool],
    *,
    max_polls: int | None = None,
) -> list[Message]:
    """Re-read the case until ``ready`` or the short wait ends. The push may never arrive."""

    fresh = chat
    polls = _PULL_TRIES if max_polls is None else min(max_polls, _PULL_TRIES)
    for attempt in range(polls):
        try:
            fresh = await city.history(need_id=need_id)
        except CapError:
            fresh = chat
        if ready(fresh):
            return fresh
        if attempt + 1 < polls:
            await asyncio.sleep(_PULL_PAUSE)
    return fresh


# The world reply is in the case history as soon as the Relay accepts it; the push that would open the
# next turn comes 60-90 s later or not at all. Read it here, bounded by real time, like `prescribed`.
_WORLD_WAIT = 180.0
_WORLD_STEP = 1.0


async def _gp_wait_world(city: City, need_id: str | None, chat: list[Message]) -> list[Message]:
    fresh, errors, started, first = chat, 0, monotonic(), True
    while first or monotonic() - started < _WORLD_WAIT:
        first = False
        try:
            fresh = await city.history(need_id=need_id)
            errors = 0
        except CapError:
            errors += 1
            if errors >= 3:
                break
        if _gp_world_received(fresh):
            return fresh
        await asyncio.sleep(_WORLD_STEP if monotonic() - started < 30 else 2 * _WORLD_STEP)
    return fresh


def _rx(need_id: str, citizen: str, renewal: str | None) -> str:
    identity = "\0".join((need_id, citizen, renewal or ""))
    suffix = sha256(identity.encode("utf-8")).hexdigest()[:20].upper()
    return f"prescription_number-{suffix}"


# --- medico di base ----------------------------------------------------------------------------


def _emergency(message: Message) -> bool:
    if understood(message).body.get("is_emergency") is True:
        return True
    lowered = message.text.lower()
    return any(flag in lowered for flag in _RED_FLAGS)


def _gp_case(chat: list[Message], inbound: Message) -> list[Message]:
    key = inbound.need_id or inbound.msg_id
    outgoing = _GP_OUTBOX.get(key, ())
    actual = {row.msg_id: row for row in chat}
    sent_ids = {row.msg_id for row in outgoing}
    rows = [row for row in chat if row.msg_id not in sent_ids]
    rows.extend(actual.get(row.msg_id, row) for row in outgoing)
    # The case is the whole need: Ledger replies can arrive in their own conversation.
    return [row for row in rows if row.need_id == inbound.need_id]


async def _gp_send(city: City, inbound: Message, to: str, text: str) -> bool:
    try:
        msg_id = await city.say(to, text)
    except CapError:
        return False
    key = inbound.need_id or inbound.msg_id
    if key not in _GP_OUTBOX:
        _GP_OUTBOX[key] = deque(maxlen=12)
    _GP_OUTBOX.move_to_end(key)
    _GP_OUTBOX[key].append(Message(
        type="chat", sender=city.agent_id, msg_id=msg_id, recipient=to,
        need_id=inbound.need_id, conversation_id=inbound.conversation_id, body={"text": text},
    ))
    if len(_GP_OUTBOX) > _SENT_NEEDS:
        _GP_OUTBOX.popitem(last=False)
    return True


def _gp_field(value: object) -> str | None:
    return value if isinstance(value, str) and _GP_FIELD.fullmatch(value) else None


def _gp_request(chat: list[Message], citizen: str) -> tuple[str | None, str | None]:
    latest_code = None
    for row in reversed(chat):
        if row.sender != citizen:
            continue
        request = understood(row)
        if request.type not in {"need.request", "data.response"}:
            continue
        code = _gp_field(request.body.get("symptom_code"))
        renewal = _gp_field(request.body.get("prescription_number"))
        if renewal and not request.body.get("symptom_code"):
            return None, renewal
        if latest_code is None and code and code.startswith("SYM-"):
            latest_code = code
    if latest_code is None:
        latest_code = _gp_keyword_code(chat, citizen)
    return latest_code, None


def _gp_keyword_code(chat: list[Message], citizen: str) -> str | None:
    for row in reversed(chat):
        if row.sender != citizen:
            continue
        lowered = (row.text or "").lower()
        for code, phrases in _GP_KEYWORDS:
            if any(phrase in lowered for phrase in phrases):
                return code
    return None


def _gp_protocols(chat: list[Message]) -> dict[str, tuple[str, str]]:
    rules: dict[str, tuple[str, str]] = {}
    for row in chat:
        if row.sender != LEDGER:
            continue
        structured = row.body.get("protocols")
        if isinstance(structured, list):
            entries = [item for item in structured if isinstance(item, dict)]
        elif first_word(row.text) in {"world", "slots", "catalogue", "protocol", "protocols"}:
            entries = [fields_of(line) for line in row.text.splitlines()]
        else:
            continue
        for entry in entries:
            code = _gp_field(entry.get("symptom_code"))
            procedure = _gp_field(entry.get("procedure"))
            priority = _gp_field(entry.get("priority"))
            if code and procedure and priority in _GP_PRIORITIES:
                rules[code] = (procedure, priority)
    return rules


def _gp_world_red_flags(chat: list[Message]) -> set[str]:
    """Red-flag phrases from the protocol table in ``world`` (list, or text split by , ; |)."""

    flags: set[str] = set()
    for row in chat:
        if row.sender != LEDGER:
            continue
        structured = row.body.get("protocols")
        if isinstance(structured, list):
            values = [item.get("red_flags") for item in structured if isinstance(item, dict)]
        elif first_word(row.text) in {"world", "slots", "catalogue", "protocol", "protocols"}:
            values = [fields_of(line).get("red_flags") for line in row.text.splitlines()]
        else:
            continue
        for value in values:
            items = value if isinstance(value, (list, tuple)) else re.split(r"[,;|]", value or "")
            for item in items:
                phrase = str(item).replace("_", " ").replace("-", " ").strip().lower()
                if len(phrase) >= 4:
                    flags.add(phrase)
    return flags


def _flag_in(flag: str, text: str) -> bool:
    """The world's red flag in the citizen's words: the phrase, or two thirds of its words (by their
    first five letters) in any order ("ho perso forza nelle gambe" for "perdita di forza alle gambe")."""
    if flag in text:
        return True
    stems = [word[:5] for word in re.findall(r"[a-zà-ù]+", flag) if len(word) >= 5]
    have = {word[:5] for word in re.findall(r"[a-zà-ù]+", text) if len(word) >= 5}
    return len(stems) >= 2 and sum(stem in have for stem in stems) * 3 >= len(stems) * 2


def _gp_world_emergency(chat: list[Message], citizen: str) -> bool:
    flags = _gp_world_red_flags(chat)
    return bool(flags) and any(
        row.sender == citizen and any(_flag_in(flag, row.text.lower()) for flag in flags) for row in chat
    )


def _gp_world_received(chat: list[Message]) -> bool:
    return any(_gp_is_world(row) for row in chat)


def _gp_is_world(row: Message) -> bool:
    return row.sender == LEDGER and (
        first_word(row.text) in {"world", "slots", "catalogue", "protocol", "protocols"}
        or isinstance(row.body.get("protocols"), list)
    )


# Console 21/11 04:18-05:12: 84 world replies out of 84 were a slot page with no protocol table and no
# red flag, and the Ledger answered 7-9 real minutes after the request: waiting for world before every
# prescription cost each citizen a Ledger round trip (agenda hours of its B window). The world is the same
# for the whole wave, so one reading serves every citizen of that wave for ten minutes.
_WORLD_SECONDS = 600
_WORLD: dict[str, tuple[list[Message], float]] = {}


def _gp_shared_world(chat: list[Message], citizen: str) -> list[Message]:
    """Remember this case's world for its wave; without one, put the wave's recent world before the chat."""
    wave = citizen.removeprefix("citizen:").split("-", 1)[0]
    own = [row for row in chat if _gp_is_world(row)
           and fields_of(row.text.splitlines()[0] if row.text else "").get("wave_id") == wave]
    if own:
        _WORLD[wave] = (own, monotonic())
        return chat
    if _gp_world_received(chat) or wave not in _WORLD:
        return chat
    rows, read = _WORLD[wave]
    return [*rows, *chat] if monotonic() - read <= _WORLD_SECONDS else chat


def _gp_ledger_rx(chat: list[Message], number: str, *, heads: set[str]) -> Message | None:
    for row in reversed(chat):
        if row.sender != LEDGER:
            continue
        act = first_word(row.text) if row.type == "chat" else row.type
        values = fields_of(row.text) if row.type == "chat" else row.body
        if act in heads and values.get("prescription_number") == number:
            return row
    return None


async def _gp_lookup(city: City, message: Message, chat: list[Message], number: str) -> Message | None:
    result = _gp_ledger_rx(chat, number, heads={"prescription"})
    if result is not None:
        return result
    query = f"prescription prescription_number={number}"
    if not _exact(chat, city.agent_id, query) and not await _gp_send(city, message, LEDGER, query):
        return None
    fresh = await _until(
        city, message.need_id, chat,
        lambda rows: _gp_ledger_rx(rows, number, heads={"prescription"}) is not None,
        max_polls=8,
    )
    return _gp_ledger_rx(_gp_case(fresh, message), number, heads={"prescription"})


def _gp_attempt(chat: list[Message], agent: str, citizen: str, number: str) -> dict[str, str]:
    for row in reversed(chat):
        if row.sender == agent and row.recipient == LEDGER and first_word(row.text) == "prescribe":
            command = fields_of(row.text)
            if command.get("patient") == citizen and command.get("prescription_number") == number:
                return command
    return {}


async def _gp_clarify(city: City, message: Message, chat: list[Message], citizen: str) -> None:
    if message.sender == citizen and not any(
        row.sender == city.agent_id and row.recipient == citizen and row.text == _GP_CLARIFICATION
        for row in chat
    ):
        await _gp_send(city, message, citizen, _GP_CLARIFICATION)


async def _gp(city: City, message: Message, chat: list[Message], *, urgent: bool = False) -> None:
    if message.sender != LEDGER and not message.sender.startswith("citizen:"):
        return
    if not message.need_id:
        return
    chat = _gp_case(chat, message)
    citizen = next((row.sender for row in chat if row.sender.startswith("citizen:")), None)
    if citizen is None or message.sender not in {citizen, LEDGER}:
        return
    chat = _gp_shared_world(chat, citizen)
    agent = city.agent_id
    if _we(chat, agent, "escalate.emergency", to=citizen, word="escalate.emergency"):
        return
    # Scan the whole citizen history: the keyword fallback reads it too, so a red flag in an
    # older message must escalate before any prescription.
    if (urgent or any(row.sender == citizen and _emergency(row) for row in chat)
            or _gp_world_emergency(chat, citizen)):
        await _gp_send(city, message, citizen, "escalate.emergency reason=red_flag")
        return

    if message.sender == LEDGER:
        act = first_word(message.text) if message.type == "chat" else message.type
        values = fields_of(message.text) if message.type == "chat" else message.body
        if act in {"prescription", "prescribed", "refused"}:
            number = _gp_field(values.get("prescription_number"))
            if number and (command := _gp_attempt(chat, agent, citizen, number)):
                await _gp_announce(city, message, chat, citizen, command)
                chat = _gp_case(chat, message)
            if act != "prescription":
                return

    code, renewal = _gp_request(chat, citizen)
    if not code and not renewal:
        await _gp_clarify(city, message, chat, citizen)
        return

    number = _rx(message.need_id, citizen, renewal)
    token = f"prescription_number={number}"
    if number == renewal or _we(chat, agent, token, to=citizen, word="prescription"):
        return
    command = _gp_attempt(chat, agent, citizen, number)
    if not command:
        protocol = await _gp_select_protocol(city, message, chat, citizen, code, renewal)
        # Level 8 hides red flags: the protocol table in world lists them per symptom.
        try:
            fresh = _gp_shared_world(_gp_case(await city.history(need_id=message.need_id), message), citizen)
        except CapError:
            fresh = chat
        if not renewal and _gp_world_emergency(fresh, citizen):
            await _gp_send(city, message, citizen, "escalate.emergency reason=red_flag")
            return
        if protocol is None:
            return
        procedure, priority = protocol
        text = f"prescribe patient={citizen} procedure={procedure} priority={priority} {token}"
        if code:
            text += f" symptom_code={code}"
        if not await _gp_send(city, message, LEDGER, text):
            return
        command = fields_of(text)
        chat = await _gp_wait_rx(city, message.need_id, chat, number)
        chat = _gp_case(chat, message)

    if code and command.get("symptom_code") != code:
        return
    await _gp_announce(city, message, chat, citizen, command)


# The Ledger's `prescribed` lands in the case history as soon as the Relay accepts it, but the push that
# would open our next turn comes 60-90 s later or not at all (405, 21/11 11:13 UTC: prescription on the
# Ledger, never announced, the citizen never reached the CUP). After `prescribe` the turn reads the
# history once a second for up to _RX_WAIT seconds (the hospital waits 180 s the same way).
_RX_WAIT = 420.0  # the Ledger answered in 208-217 s at 10:06 UTC (consultorio 1.0.11 waits 420 s too)
_RX_STEP = 1.0


async def _gp_wait_rx(city: City, need_id: str | None, chat: list[Message], number: str) -> list[Message]:
    """Bounded by real time (a slow history read must not stretch the turn) and by 3 errors in a row."""
    fresh, errors, started, first = chat, 0, monotonic(), True
    while first or monotonic() - started < _RX_WAIT:
        first = False
        try:
            fresh = await city.history(need_id=need_id)
            errors = 0
        except CapError:
            errors += 1
            if errors >= 3:
                break
        if _gp_ledger_rx(fresh, number, heads={"prescribed", "refused"}) is not None:
            return fresh
        await asyncio.sleep(_RX_STEP)
    _LOG.warning("gp.prescribed.late need=%s rx=%s", need_id, number[-8:])
    return fresh


async def _gp_announce(
    city: City, message: Message, chat: list[Message], citizen: str, command: dict[str, str]
) -> None:
    agent = city.agent_id
    number = command["prescription_number"]
    reply = _gp_ledger_rx(chat, number, heads={"prescribed", "refused"})
    if reply is None:
        # The Ledger may answer with its own prescription_number: accept only a `prescribed`
        # line for this citizen and this procedure, never an unrelated Ledger line.
        for row in reversed(chat):
            if row.sender != LEDGER:
                continue
            act = first_word(row.text) if row.type == "chat" else row.type
            values = fields_of(row.text) if row.type == "chat" else row.body
            owner = values.get("patient") or values.get("citizen")
            if act == "prescribed" and owner == citizen and values.get("procedure") == command["procedure"]:
                reply = row
                break
    if reply is None:
        # No Ledger confirmation yet: never announce a prescription the Ledger has not written.
        # The Ledger reply (its own turn, or the citizen's next message) brings us back here.
        return
    values = fields_of(reply.text) if reply.type == "chat" else reply.body
    act = first_word(reply.text) if reply.type == "chat" else reply.type
    duplicate = values.get("code") == "DUPLICATE" or "DUPLICATE" in reply.text.split()
    if act == "refused" and not duplicate:
        failure = ("Mi dispiace, il registro non ha accettato la ricetta. "
                   "Mi riscriva il disturbo e riprovo subito.")
        if not any(row.sender == agent and row.recipient == citizen and row.text == failure
                   for row in chat):
            await _gp_send(city, message, citizen, failure)
        return
    if act == "refused":
        # DUPLICATE: the prescription may exist. Announce it only after reading it back.
        found = await _gp_lookup(city, message, chat, number)
        if found is None:
            return
        stored = fields_of(found.text) if found.type == "chat" else found.body
        owner = stored.get("patient") or stored.get("citizen")
        if (owner and owner != citizen) or stored.get("state", "issued") != "issued":
            return
    ledger_number = _gp_field(values.get("prescription_number"))
    if act == "prescribed" and ledger_number:
        number = ledger_number
    # One announcement per prescription number (a renewal has a new number and is announced).
    if any(row.sender == agent and row.recipient == citizen and first_word(row.text) == "prescription"
           and fields_of(row.text).get("prescription_number") == number for row in chat):
        return
    notice = (f"prescription prescription_number={number} procedure={command['procedure']} "
              f"priority={command['priority']} "
              "Grazie per avermi scritto. La ricetta è registrata: con questo numero può prenotare "
              "la visita al centro prenotazioni (CUP). Indichi lingua, giorni e zona che preferisce, "
              "così le propongono l'orario più comodo.")
    _LOG.info("gp need=%s announce %s", (message.need_id or "")[-12:], number)
    await _gp_send(city, message, citizen, notice)


async def _gp_select_protocol(
    city: City, message: Message, chat: list[Message], citizen: str,
    code: str | None, renewal: str | None,
) -> tuple[str, str] | None:
    if renewal:
        old = await _gp_lookup(city, message, chat, renewal)
        if old is None:
            return None
        values = fields_of(old.text) if old.type == "chat" else old.body
        owners = [values[key] for key in ("patient", "citizen") if key in values]
        if any(owner != citizen for owner in owners):
            return None
        if not owners and not _gp_attempt(chat, city.agent_id, citizen, renewal):
            return None
        if values.get("state") not in {"issued", "expired"}:
            return None
        procedure = _gp_field(values.get("procedure"))
        priority = _gp_field(values.get("priority"))
        return (procedure, priority) if procedure and priority in _GP_PRIORITIES else None

    if not code:
        return None
    if not _gp_world_received(chat):
        if not _exact(chat, city.agent_id, "world") and not await _gp_send(city, message, LEDGER, "world"):
            return None
        fresh = await _gp_wait_world(city, message.need_id, chat)
        chat = _gp_case(fresh, message)
    if not _gp_world_received(chat):
        # Never prescribe before reading world: level 8 hides red flags in its protocol table. The
        # wait is 6 s (was 2 s: a slow world left the GP silent, 201); the world's own turn resumes.
        return None
    # The local SDK's world can explicitly answer with slots and no protocol table.
    return _gp_protocols(chat).get(code) or _PROTOCOLS.get(code)


# --- centro prenotazioni and consultorio -------------------------------------------------------


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

    __slots__ = ("offers", "trigger", "again")

    def __init__(self) -> None:
        self.offers: set[str] = set()
        self.trigger = ""
        self.again: set[str] = set()


# Every Ledger or citizen message opens its own turn, and turns of one need run at the same
# time. Each reads the case before the others' offers are in it, so offers wait on this.
# An entry lives only while a turn holds or waits on its lock.
_GATES: dict[str, _Gate] = {}
_SENT: OrderedDict[str, _Sent] = OrderedDict()


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


# --- facility ----------------------------------------------------------------------------------


