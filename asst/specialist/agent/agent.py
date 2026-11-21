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
    Friday it goes on from Monday (kit, ADR-124). B on a Thursday ends on Monday, not on Saturday."""

    at = now
    left = days
    while left > 0:
        at += timedelta(days=1)
        if at.weekday() < 5:
            left -= 1
    return at


_RX = re.compile(r"^prescription_number-[A-Z0-9-]{4,40}$")
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


async def main(need: Need, city: City) -> None:
    message = city.inbound
    if message is None:
        return
    text = message.text or need.summary
    if clinical(text):
        raise OutOfScope()
    case = await _turn_history(city, message.need_id)
    if case is None:
        return  # no case data: never commit, report or send a receipt on a partial view
    await handle(role_of(), city, message, case)


async def _turn_history(city: City, need_id: str | None) -> list[Message] | None:
    """The case at the start of the turn. A 5xx (e.g. 504 UPSTREAM_TIMEOUT) is retried once after
    a short pause, so a late held line still gets its commit in this turn (#107); a 4xx is not
    retried; a second failure ends the turn without any effect."""
    for attempt in range(2):
        try:
            return await city.history(need_id=need_id)
        except CapError as error:
            try:
                transient = error.http_status() >= 500
            except CapError:
                transient = False
            _LOG.warning("care.history.error need=%s code=%s attempt=%d", need_id, error.code, attempt + 1)
            if not transient or attempt:
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
    # This file serves only the specialist (and the hospital as a fallback): the other roles'
    # code was removed to keep the brain small for the city's deploy scan.
    if role in {"specialist_care", "hospital"}:
        await _facility(city, message, chat, reports=role == "specialist_care", hold_self=False)


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


# --- medico di base ----------------------------------------------------------------------------


# --- centro prenotazioni and consultorio -------------------------------------------------------


def _our_offer(chat: list[Message], agent: str, offer_id: str) -> dict[str, str]:
    token = f"offer_id={offer_id}"
    for row in chat:
        if row.sender == agent and token in row.text.split() and "offer" in words(row.text):
            return fields_of(row.text)
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


async def _on_confirm(
    city: City, message: Message, chat: list[Message], *, hold_self: bool
) -> None:
    agent = city.agent_id
    fields = fields_of(message.text)
    offer_id = fields.get("offer_id", "")
    # Rule P2 (live from 21/11, agenda 29/12 08:00): a hold in another ASST needs the cross_asst consent,
    # else the Ledger refuses CONSENT_MISSING. Booking centres that send the booking consent in consent_ref
    # put it in cross_asst_consent_ref (MACH-1.x) or cross_consent_ref (our CUP): that one goes on the hold.
    consent = fields.get("cross_asst_consent_ref") or fields.get("cross_consent_ref") or fields.get("consent_ref", "")
    offer = _our_offer(chat, agent, offer_id) if offer_id else {}
    slot = fields.get("slot_id") or offer.get("slot_id", "")
    facility = fields.get("facility") or offer.get("facility", "")
    if not slot or not consent:
        return
    citizen = fields.get("citizen") or (
        message.sender if message.sender.startswith("citizen:") else ""
    )
    number = fields.get("prescription_number") or offer.get("prescription_number")
    book_here = hold_self or message.sender.startswith("agent:") or facility == agent
    if book_here:
        if not _we(chat, agent, f"slot_id={slot}", to=LEDGER, word="hold"):
            parts = ["hold", f"slot_id={slot}"]
            if citizen:
                parts.append(f"citizen={citizen}")
            if number:
                parts.append(f"prescription_number={number}")
            parts.append(f"consent_ref={consent}")
            if not await _say(city, LEDGER, " ".join(parts)):
                return
        await _finish_booking(city, message, chat, slot, hold_self=hold_self)
        return
    if not facility or not citizen:
        return
    if _we(chat, agent, f"slot_id={slot}", to=facility, word="confirm"):
        return
    parts = [
        "confirm",
        f"offer_id={offer_id or offer.get('offer_id', '')}",
        f"slot_id={slot}",
        f"citizen={citizen}",
        f"consent_ref={consent}",
        f"facility={facility}",
    ]
    if number:
        parts.append(f"prescription_number={number}")
    await _say(city, facility, " ".join(parts))


# --- facility ----------------------------------------------------------------------------------


async def _facility(
    city: City,
    message: Message,
    chat: list[Message],
    *,
    reports: bool,
    hold_self: bool,
) -> None:
    head = first_word(message.text)
    kind = words(message.text)
    if not (message.sender == LEDGER and head == "held"):
        await _commit_late_holds(city, message, chat)
    if message.sender.startswith("agent:") and head == "need.request":
        await _answer_partner_search(city, message)
    elif message.sender == LEDGER and head == "held":
        await _on_held(city, message, chat)
    elif message.sender == LEDGER and head == "committed":
        await _on_committed(city, message, chat)
    elif message.sender == LEDGER and head == "refused" and kind & {"hold", "commit"}:
        await _on_refused(city, message, chat, hold_self=hold_self)
    elif message.sender == LEDGER and head == "checked_in":
        await _on_checked_in(city, message, chat, reports=reports)
    elif message.sender == LEDGER and head == "reported":
        await _on_reported(city, message, chat)
    elif "checkin" in kind and message.sender.startswith("citizen:"):
        await _on_checkin(city, message, chat, reports=reports)
    elif reports and message.sender.startswith("citizen:") and _consent_pending(chat, city.agent_id):
        await _on_report_consent(city, message, chat)
    elif "confirm" in kind:
        await _on_confirm(city, message, chat, hold_self=hold_self)


# --- ricerca dai centri prenotazioni di altre ASST (formato comune del livello 4, MACH-1.x) -----
# need.request service_type=specialist_care.cardiology procedure=VIS-CARD priority=B request_id=...
# [lang=] [gender_preference=] [days=mon/wed]: one message back, offer lines or a cancel. No citizen
# data travels here; the confirm that follows (after the cross_asst consent) goes to _on_confirm.
_SPEC_DOCTORS = {  # registry, asst-bicocca
    "asst-bicocca-s1": ("it/en", "m", frozenset({"mon", "wed", "fri"})),
    "asst-bicocca-s2": ("it", "f", frozenset({"tue", "thu"})),
}
_SPEC_PROCEDURES = frozenset({"VIS-CARD", "CTRL-CARD"})
_WEEK = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_ANSWERED_SEARCHES: OrderedDict[str, None] = OrderedDict()


def _search_when(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _search_slots(slots_text: str, *, now: datetime, me: str, fields: dict[str, str]) -> list[dict[str, str]]:
    priority = (fields.get("priority") or "").upper()
    if priority == "U":
        horizon: datetime | None = now.replace(hour=23, minute=59, second=59, microsecond=0)
    elif priority == "P":
        horizon = None
    else:
        horizon = _agenda_horizon(now, _DEADLINE_DAYS.get(priority, 14))
    lang = fields.get("lang", "").lower()
    gender = (fields.get("gender_preference") or fields.get("gender") or "").lower()
    days = set(re.split(r"[/,;\s]+", fields.get("days", "").lower())) & set(_WEEK)
    chosen: list[tuple[datetime, dict[str, str]]] = []
    for line in slots_text.splitlines():
        slot = fields_of(line)
        at = _search_when(slot.get("at", "") or slot.get("agenda_date", ""))
        if not slot.get("slot_id") or at is None or slot.get("facility", me) != me:
            continue
        if not now + _LEAD < at or (horizon is not None and at >= horizon):
            continue
        free = slot.get("free", slot.get("capacity", "1"))
        if not free.isdecimal() or int(free) <= 0:
            continue
        if slot.get("urgent_reserve", "").lower() == "true" and priority != "U":
            continue
        doctor = _SPEC_DOCTORS.get(slot.get("doctor_id", ""))
        day = _WEEK[at.weekday()]
        if doctor is None or day not in doctor[2] or (days and day not in days):
            continue
        if (lang and lang not in doctor[0].split("/")) or (gender in {"m", "f"} and gender != doctor[1]):
            continue
        slot["at"], slot["day"] = at.isoformat(), day
        chosen.append((at, slot))
    chosen.sort(key=lambda item: (item[0], item[1]["slot_id"]))
    return [slot for _, slot in chosen]


async def _answer_partner_search(city: City, message: Message) -> None:
    fields = fields_of(message.text)
    rid = fields.get("request_id", "")
    if not rid or rid in _ANSWERED_SEARCHES:
        return
    _ANSWERED_SEARCHES[rid] = None
    if len(_ANSWERED_SEARCHES) > _SENT_NEEDS:
        _ANSWERED_SEARCHES.popitem(last=False)
    service, procedure = fields.get("service_type", ""), fields.get("procedure", "") or "VIS-CARD"
    if (service and not service.startswith("specialist_care")) or procedure not in _SPEC_PROCEDURES:
        await _say(city, message.sender, f"cancel reason=procedure_not_offered request_id={rid}")
        return
    await _say(city, LEDGER, "agenda")
    await _say(city, LEDGER, f"world procedure={procedure} page=1")
    slots_text, now = None, None
    for attempt in range(_PULL_TRIES):
        try:
            rows = await city.history(need_id=message.need_id)
        except CapError:
            rows = []
        for row in rows:
            if row.sender != LEDGER:
                continue
            if first_word(row.text) == "slots" and f"procedure={procedure}" in row.text:
                slots_text = row.text
            elif first_word(row.text) == "agenda":
                now = _search_when(fields_of(row.text).get("agenda_now", "")) or now
        if slots_text and now:
            break
        if attempt + 1 < _PULL_TRIES:
            await asyncio.sleep(_PULL_PAUSE)
    if not slots_text or now is None:
        await _say(city, message.sender, f"cancel reason=facility_unavailable request_id={rid}")
        return
    me = city.agent_id
    lines = []
    for slot in _search_slots(slots_text, now=now, me=me, fields=fields)[:3]:
        lang, sex, _ = _SPEC_DOCTORS[slot["doctor_id"]]
        lines.append(
            f"offer offer_id=of-{slot['slot_id']} slot_id={slot['slot_id']} doctor_id={slot['doctor_id']} "
            f"facility={me} procedure={procedure} agenda_date={slot['at']} agenda_day={slot['day']} "
            f"expiry={slot['at']} doctor_lang={lang} doctor_gender={sex} request_id={rid}"
        )
    if not lines:
        lines = [f"cancel reason=no_availability request_id={rid} procedure={procedure}"]
    await _say(city, message.sender, "\n".join(lines))


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
        _LOG.warning("care.held.missing need=%s slot=%s", message.need_id, slot)
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


async def _commit_late_holds(city: City, message: Message, chat: list[Message]) -> None:
    """A held line that came after the confirm turn stopped waiting (Ledger 7-9 min late) never
    got its commit, and the hold expired (2190006, 3370003, 2620005). Any later turn of the case
    commits a held hold of ours that has no commit and no refusal yet."""
    agent = city.agent_id
    for row in chat:
        if row.sender != LEDGER or first_word(row.text) != "held":
            continue
        hold_id = fields_of(row.text).get("hold_id", "")
        if not hold_id or _our_commit(chat, agent, hold_id):
            continue
        token = f"hold_id={hold_id}"
        if any(r.sender == LEDGER and first_word(r.text) in {"refused", "committed", "expired"} and token in r.text.split()
               for r in chat):
            continue
        _LOG.warning("care.held.late need=%s hold=%s", message.need_id, hold_id)
        await _on_held(city, row, chat)


async def _on_held(city: City, message: Message, chat: list[Message]) -> None:
    fields = fields_of(message.text)
    hold_id = fields.get("hold_id", "")
    slot = fields.get("slot_id", "")
    if not hold_id or not slot:
        _LOG.info("care.held.skip", extra={"head": first_word(message.text)[:40]})
        return
    if _our_commit(chat, city.agent_id, hold_id):
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
    await _say(city, LEDGER, " ".join(parts))


async def _on_committed(city: City, message: Message, chat: list[Message]) -> None:
    fields = fields_of(message.text)
    booking_id = fields.get("booking_id", "")
    ledger_ref = fields.get("ledger_ref", "")
    if not booking_id or not ledger_ref:
        return
    slot = fields.get("slot_id") or _hold_slot(chat, city.agent_id, fields.get("hold_id", ""))
    sender, _, _ = _booking_of(chat, city.agent_id, slot) if slot else ("", "", None)
    target = sender or _citizen(chat)
    if not target:
        return
    token = f"booking_id={booking_id}"
    if _we(chat, city.agent_id, token, to=target, word="booking.receipt"):
        return
    line = f"booking.receipt booking_id={booking_id} ledger_ref={ledger_ref}"
    if slot:
        # Cross-ASST: the booking centre matches the receipt to its confirm by slot and offer.
        offer_id = next(
            (fields_of(row.text).get("offer_id", "") for row in reversed(chat)
             if row.sender == target and f"slot_id={slot}" in row.text.split() and "confirm" in words(row.text)),
            "",
        )
        line += f" slot_id={slot}" + (f" offer_id={offer_id}" if offer_id else "")
    await _say(city, target, line)


async def _on_refused(
    city: City, message: Message, chat: list[Message], *, hold_self: bool
) -> None:
    """A Ledger refusal cancels the offer it refers to, never the latest one.

    A refusal can arrive late, after a newer hold for the same citizen: match it by its own
    slot_id or hold_id, keep the Ledger code, and never cancel after a valid receipt."""
    agent = city.agent_id
    refused = fields_of(message.text)
    code = (refused.get("code") or refused.get("reason") or refused.get("error")
            or next((t for t in message.text.split() if re.fullmatch(r"[A-Z][A-Z_]{3,}", t)), ""))
    if "commit" in words(message.text) and (code.upper() == "DUPLICATE" or "DUPLICATE" in message.text.split()):
        return  # the hold is already committed: the booking stands
    slot = refused.get("slot_id") or _hold_slot(chat, agent, refused.get("hold_id", ""))
    if not slot and not (refused.get("slot_id") or refused.get("hold_id")):
        for row in chat:  # no identifier at all: the only hold we can mean is the last one
            if row.sender == agent and row.recipient == LEDGER and first_word(row.text) == "hold":
                slot = fields_of(row.text).get("slot_id", slot)
    if not slot:
        return
    target, _, _ = _booking_of(chat, agent, slot)
    if not target or _receipt_sent(chat, agent, target, slot):
        return  # never cancel after a valid receipt
    offer_id = ""
    for row in chat:
        if row.sender == target and f"slot_id={slot}" in row.text.split() and "confirm" in words(row.text):
            offer_id = fields_of(row.text).get("offer_id", offer_id)
    if not offer_id:
        offer_id = _our_offer_for_slot(chat, agent, slot)
    if not offer_id or _we(chat, agent, f"offer_id={offer_id}", to=target, word="cancel")             or _we(chat, agent, f"offer_id={offer_id}", to=target, word="hold_refused"):
        return
    known = {"PRESCRIPTION_EXPIRED", "CONSENT_MISSING", "NO_CAPACITY"}
    if target.startswith("agent:"):
        # MACH-1.2 towards a booking centre: lower-case reason for the three known codes.
        if code in known:
            line = f"cancel offer_id={offer_id} slot_id={slot} reason={code.lower()}"
        elif code:
            line = f"hold_refused offer_id={offer_id} slot_id={slot} ledger_code={code}"
        else:
            line = f"cancel offer_id={offer_id} slot_id={slot} reason=facility_cancelled"
    else:
        line = f"cancel offer_id={offer_id} slot_id={slot} reason={code or 'facility_cancelled'}"
    await _say(city, target, line)


def _receipt_sent(chat: list[Message], agent: str, target: str, slot: str) -> bool:
    """A booking.receipt already went to ``target`` for this slot. Receipts to a citizen may carry no
    slot_id (older ones), so any receipt to the citizen after its confirm for this slot counts."""
    confirmed = False
    for row in chat:
        if row.sender == target and f"slot_id={slot}" in row.text.split() and "confirm" in words(row.text):
            confirmed = True
        if row.sender == agent and row.recipient == target and first_word(row.text) == "booking.receipt":
            if f"slot_id={slot}" in row.text.split() or (confirmed and target.startswith("citizen:")):
                return True
    return False


def _our_offer_for_slot(chat: list[Message], agent: str, slot: str) -> str:
    offer_id = ""
    for row in chat:
        if row.sender == agent and f"slot_id={slot}" in row.text.split():
            offer_id = fields_of(row.text).get("offer_id", offer_id)
    return offer_id


async def _on_checkin(city: City, message: Message, chat: list[Message], *, reports: bool) -> None:
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
        await _on_checked_in(city, reply, fresh, reports=reports)


async def _on_checked_in(
    city: City, message: Message, chat: list[Message], *, reports: bool
) -> None:
    booking_id = fields_of(message.text).get("booking_id", "")
    citizen = _citizen(chat)
    if not booking_id:
        return
    token = f"booking_id={booking_id}"
    if citizen and not _we(chat, city.agent_id, token, to=citizen, word="checkin"):
        ledger_ref = fields_of(message.text).get("ledger_ref")
        await _say(city, citizen, f"checkin booking_id={booking_id}" + (f" ledger_ref={ledger_ref}" if ledger_ref else ""))
    if not reports:
        return
    # Ask report_sharing consent, wait a short while for the answer, then archive the report in any
    # case: shared with a report_sharing consent_ref, otherwise not shared. Waiting for an answer that
    # never comes left the report unfiled (report_missing -1, journey 1820005: the citizen does not
    # answer after the check-in). The kit: without the requested field, archive the report unshared.
    if citizen and not _we(chat, city.agent_id, "purpose=report_sharing", to=citizen, word="consent"):
        await _say(
            city, citizen,
            f"consent purpose=report_sharing {token} La visita è registrata. "
            "Posso condividere il referto con il suo medico di base? Se non mi risponde subito, "
            "lo archivio senza condividerlo.",
        )
    if not citizen:
        return
    fresh = chat
    deadline = asyncio.get_running_loop().time() + _CONSENT_WAIT
    while True:
        answered, consent_ref = _consent_answer(fresh, city.agent_id, citizen)
        if answered or asyncio.get_running_loop().time() >= deadline:
            break
        await asyncio.sleep(_PULL_PAUSE)
        try:
            fresh = await city.history(need_id=message.need_id)
        except CapError:
            pass
    await _file_report(city, message, fresh, booking_id, consent_ref)


_CONSENT_ASK = "purpose=report_sharing"
# How long the check-in turn waits for the answer to the consent question before archiving.
_CONSENT_WAIT = 2.0  # the conformance health check (p99) fails with a 20 s wait in the turn
# Bookings whose report this process already sent to the Ledger (parallel-turn guard).
_REPORT_SENT: set[str] = set()


def _consent_reply(message: Message) -> tuple[bool, str]:
    """(is an answer to our report_sharing question, consent_ref). A consent for another purpose
    (booking, cross_asst...) is not an answer; plain words without consent_ref are a refusal."""

    body = understood(message).body
    fields = fields_of(message.text)
    consent_ref = fields.get("consent_ref") or body.get("consent_ref")
    purpose = fields.get("purpose") or body.get("purpose")
    if not isinstance(consent_ref, str):
        consent_ref = ""
    if consent_ref and purpose != "report_sharing" and not consent_ref.endswith("report_sharing"):
        return False, ""
    return True, consent_ref


def _consent_answer(chat: list[Message], agent: str, citizen: str) -> tuple[bool, str]:
    """The citizen's answer after our last report_sharing question, if it is in the history."""

    asked = None
    for index, row in enumerate(chat):
        if row.sender == agent and first_word(row.text) == "consent" and _CONSENT_ASK in row.text.split():
            asked = index
    if asked is None:
        return False, ""
    for row in chat[asked + 1:]:
        if row.sender == citizen:
            answered, consent_ref = _consent_reply(row)
            if answered:
                return True, consent_ref
    return False, ""


def _consent_pending(chat: list[Message], agent: str) -> bool:
    """True after we asked report_sharing consent and before we sent the report to the Ledger."""

    asked = any(
        row.sender == agent and first_word(row.text) == "consent" and _CONSENT_ASK in row.text.split()
        for row in chat
    )
    reported = any(
        row.sender == agent and row.recipient == LEDGER and first_word(row.text) == "report" for row in chat
    )
    return asked and not reported


async def _on_report_consent(city: City, message: Message, chat: list[Message]) -> None:
    agent = city.agent_id
    booking_id = ""
    for row in chat:
        if row.sender == agent and first_word(row.text) == "consent" and _CONSENT_ASK in row.text.split():
            booking_id = fields_of(row.text).get("booking_id", "")
    if not booking_id:
        return
    answered, consent_ref = _consent_reply(message)
    if not answered:
        return
    await _file_report(city, message, chat, booking_id, consent_ref)


async def _file_report(
    city: City, message: Message, chat: list[Message], booking_id: str, consent_ref: str
) -> None:
    """One report per booking: shared with a report_sharing consent_ref, else archived unshared."""

    if any(
        row.sender == city.agent_id and row.recipient == LEDGER and first_word(row.text) == "report"
        and f"booking_id={booking_id}" in row.text.split()
        for row in chat
    ):
        return
    command = f"report booking_id={booking_id} outcome_code=VISIT"
    if consent_ref:
        command += f" consent_ref={consent_ref}"
    # Two turns (the check-in wait and a late answer) can run in parallel before history shows our
    # report: check and mark in-process with no await in between, so only one sends it.
    if booking_id in _REPORT_SENT:
        return
    _REPORT_SENT.add(booking_id)
    if not await _say(city, LEDGER, command):
        _REPORT_SENT.discard(booking_id)
        return
    token = f"booking_id={booking_id}"
    found = await _await_line(city, message.need_id, chat, "reported", token, op="report")
    if found is None:
        _LOG.info("care.report.missing", extra={"need_id": (message.need_id or "")[:48]})
        return
    reply, fresh = found
    if first_word(reply.text) == "reported":
        await _on_reported(city, reply, fresh)


async def _on_reported(city: City, message: Message, chat: list[Message]) -> None:
    booking_id = fields_of(message.text).get("booking_id", "")
    citizen = _citizen(chat)
    if not booking_id or not citizen:
        return
    token = f"booking_id={booking_id}"
    if _we(chat, city.agent_id, token, to=citizen, word="report"):
        return
    await _say(
        city, citizen,
        f"report booking_id={booking_id} outcome_code=VISIT Grazie per essere venuto. "
        "Il referto della visita è archiviato. Se il suo medico di base le prescrive un controllo, "
        "può prenotarlo al centro prenotazioni con la nuova ricetta.",
    )
