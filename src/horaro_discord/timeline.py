"""Pure schedule logic: item identity, current/next items, notification planning, fetch timing.

Nothing here talks to Discord or HTTP, and the current time is always passed in.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from .horaro import Item, Schedule

# A notified item is announced again only when its start moves by at least this much.
RENOTIFY_SHIFT = 5 * 60

LIVE_FETCH_INTERVAL = 60
IDLE_FETCH_INTERVAL = 30 * 60
# The live window starts this long before the first notification and ends this long after the end.
LIVE_MARGIN = 30 * 60

_KEY_COLUMN = re.compile(r"game|title|ゲーム|タイトル|作品", re.IGNORECASE)
_MD_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_MD_MARK = re.compile(r"[*_`~|>#]")
_SPACE = re.compile(r"\s+")


def strip_markdown(text: str) -> str:
    text = _MD_LINK.sub(r"\1", text)
    text = _MD_MARK.sub("", text)
    return _SPACE.sub(" ", text).strip()


def detect_key_column(columns: tuple[str, ...]) -> str | None:
    for column in columns:
        if _KEY_COLUMN.search(column):
            return column
    return columns[0] if columns else None


def effective_key_column(schedule: Schedule, key_column: str | None) -> str | None:
    if key_column in schedule.columns:
        return key_column
    return detect_key_column(schedule.columns)


def item_keys(schedule: Schedule, key_column: str | None) -> list[str]:
    """Identity of each item, stable against changes in other columns and in item order.

    Horaro items have no ID. An item is identified by the value of the key column plus how many
    items before it have the same value. Items whose key value is empty use the whole row.
    """
    column = effective_key_column(schedule, key_column)
    seen: Counter[str] = Counter()
    keys = []
    for item in schedule.items:
        value = strip_markdown(schedule.value(item, column) or "") if column else ""
        if value:
            base = "k:" + value.casefold()
        else:
            base = "r:" + "|".join(strip_markdown(v or "").casefold() for v in item.values)
        keys.append(f"{base}#{seen[base]}")
        seen[base] += 1
    return keys


def rekey(schedule: Schedule, old_column: str | None, new_column: str | None) -> dict[str, str]:
    """Map item keys under `old_column` to keys under `new_column`."""
    return dict(zip(item_keys(schedule, old_column), item_keys(schedule, new_column), strict=True))


def item_title(schedule: Schedule, item: Item, key_column: str | None) -> str:
    column = effective_key_column(schedule, key_column)
    value = schedule.value(item, column) if column else None
    if value and value.strip():
        return value.strip()
    filled = [v.strip() for v in item.values if v and v.strip()]
    return filled[0] if filled else f"#{item.index + 1}"


@dataclass(frozen=True)
class NowNext:
    """`current` is None between items (setup time), before the start and after the end."""

    current: Item | None
    next: Item | None


def now_next(schedule: Schedule, now: int) -> NowNext:
    current = None
    for item in schedule.items:
        if item.scheduled_t > now:
            return NowNext(current, item)
        if now < item.end_t:
            current = item
    return NowNext(current, None)


def upcoming(schedule: Schedule, now: int, count: int) -> list[Item]:
    """Items that have not ended yet, starting with the current one."""
    return [item for item in schedule.items if item.end_t > now][:count]


@dataclass(frozen=True)
class Record:
    """A sent notification.

    `notified_t` is the start time announced in the latest notification.
    `displayed_t` is the start time the message currently shows (differs after an edit).
    """

    item_key: str
    title: str
    notified_t: int
    displayed_t: int
    channel_id: int
    message_id: int | None
    removed: bool = False


@dataclass(frozen=True)
class Send:
    item: Item
    item_key: str
    # Start time of the previous notification when this is a re-notification.
    previous_t: int | None


@dataclass(frozen=True)
class Edit:
    """Update a sent message: `item` is None when the item was removed from the schedule."""

    record: Record
    item: Item | None


Action = Send | Edit


def plan(
    schedule: Schedule,
    keys: list[str],
    records: dict[str, Record],
    now: int,
    notice: int,
) -> list[Action]:
    """Decide which notifications to send and which sent messages to edit.

    Everything is derived from the latest schedule, so a change made after a notification was
    sent is reflected the next time this runs.
    """
    actions: list[Action] = []
    for item, key in zip(schedule.items, keys, strict=True):
        due = item.scheduled_t - notice <= now < item.scheduled_t
        record = records.get(key)
        if record is None:
            if due:
                actions.append(Send(item, key, None))
            continue
        # Messages about items that are over under both the old and new times are left alone.
        relevant = max(item.scheduled_t, record.displayed_t) > now
        if (record.removed or item.scheduled_t != record.displayed_t) and relevant:
            actions.append(Edit(record, item))
        if due and abs(item.scheduled_t - record.notified_t) >= RENOTIFY_SHIFT:
            actions.append(Send(item, key, record.notified_t))

    present = set(keys)
    for key, record in records.items():
        if key not in present and not record.removed and record.displayed_t > now:
            actions.append(Edit(record, None))
    return actions


def next_fetch_delay(schedule: Schedule | None, now: int, max_notice: int, failures: int) -> int:
    if schedule is None:
        base = LIVE_FETCH_INTERVAL
    else:
        live_from = schedule.start_t - max_notice - LIVE_MARGIN
        live_until = schedule.end_t + LIVE_MARGIN
        if now < live_from:
            # Wake up when the live window starts.
            base = max(LIVE_FETCH_INTERVAL, min(IDLE_FETCH_INTERVAL, live_from - now))
        elif now <= live_until:
            base = LIVE_FETCH_INTERVAL
        else:
            base = IDLE_FETCH_INTERVAL
    if failures:
        return min(base << min(failures, 10), IDLE_FETCH_INTERVAL)
    return base


def server_event_times(schedule: Schedule) -> tuple[int, int]:
    """Start and end of the Discord server event for a schedule (at least one minute long)."""
    return schedule.start_t, max(schedule.end_t, schedule.start_t + 60)
