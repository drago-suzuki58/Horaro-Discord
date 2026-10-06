"""Periodic loop: fetch schedules, then send and edit notifications based on the latest data."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum
from typing import Protocol

from .horaro import HoraroClient, HoraroError, Item, Schedule, parse_schedule
from .store import ScheduleRow, Store, Subscription
from .timeline import (
    LIVE_FETCH_INTERVAL,
    LIVE_MARGIN,
    Action,
    Record,
    Send,
    item_keys,
    item_title,
    next_fetch_delay,
    plan,
    server_event_times,
)

log = logging.getLogger(__name__)

TICK_INTERVAL = 30


class Kind(Enum):
    NOTICE = "notice"
    # Sent again because the start time moved after the first notification.
    RENOTICE = "renotice"
    # A sent message edited because the start time moved.
    CHANGED = "changed"
    # A sent message edited because the item disappeared from the schedule.
    REMOVED = "removed"


@dataclass(frozen=True)
class Notification:
    kind: Kind
    schedule_name: str
    link: str
    title: str
    scheduled_t: int
    # The start time announced before the change (RENOTICE, CHANGED).
    previous_t: int | None
    length_t: int | None
    details: tuple[tuple[str, str], ...]


class DiscordPort(Protocol):
    async def send(self, channel_id: int, notification: Notification) -> int | None:
        """Return the message ID, or None when the message can never be delivered."""

    async def edit(self, channel_id: int, message_id: int, notification: Notification) -> None: ...

    async def sync_server_event(
        self, guild_id: int, event_id: int, start_t: int, end_t: int
    ) -> bool:
        """Move the server event to the given times. Return False if the event is gone."""


class FetchOutcome(Enum):
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    FAILED = "failed"


def display_name(event_name: str, schedule: Schedule) -> str:
    event, name = event_name.casefold(), schedule.name.casefold()
    if event in name:
        return schedule.name
    if name in event:
        return event_name
    return f"{event_name} / {schedule.name}"


def build_notification(
    kind: Kind, row: ScheduleRow, item: Item, key_column: str | None, previous_t: int | None
) -> Notification:
    schedule = row.schedule
    title = item_title(schedule, item, key_column)
    details = tuple(
        (column, value.strip())
        for column, value in zip(schedule.columns, item.values, strict=False)
        if value and value.strip() and value.strip() != title
    )
    return Notification(
        kind=kind,
        schedule_name=display_name(row.event_name, schedule),
        link=schedule.link,
        title=title,
        scheduled_t=item.scheduled_t,
        previous_t=previous_t,
        length_t=item.length_t,
        details=details,
    )


class Scheduler:
    def __init__(
        self,
        store: Store,
        client: HoraroClient,
        discord: DiscordPort,
        clock: Callable[[], int] = lambda: int(time.time()),
    ) -> None:
        self.store = store
        self.client = client
        self.discord = discord
        self.clock = clock
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        # Times last requested per server event ID, to avoid repeating API calls.
        self._synced_events: dict[int, tuple[int, int]] = {}

    def lock(self, schedule_id: str) -> asyncio.Lock:
        """Held while a schedule's notifications are processed; take it to change its records."""
        return self._locks[schedule_id]

    async def run(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                log.exception("Scheduler tick failed")
            await asyncio.sleep(TICK_INTERVAL)

    async def tick(self) -> None:
        for schedule_id in self.store.subscribed_schedule_ids():
            try:
                await self.process(schedule_id)
            except Exception:
                log.exception("Failed to process schedule %s", schedule_id)

    async def process(self, schedule_id: str, *, force_fetch: bool = False) -> FetchOutcome | None:
        """Fetch the schedule if due, then send and edit its notifications.

        Returns the fetch outcome, or None if no fetch was needed.
        """
        async with self._locks[schedule_id]:
            row = self.store.get_schedule(schedule_id)
            if row is None:
                return None
            outcome = None
            if force_fetch or self.clock() >= row.next_fetch_at:
                outcome = await self._fetch(row)

            plans = self._plan_all(schedule_id)
            # Never announce from data older than the live polling interval.
            if outcome is None and any(isinstance(a, Send) for _, acts in plans for a in acts):
                row = self.store.get_schedule(schedule_id)
                if row and self.clock() - row.fetched_at > LIVE_FETCH_INTERVAL:
                    outcome = await self._fetch(row)
                    plans = self._plan_all(schedule_id)

            row = self.store.get_schedule(schedule_id)
            assert row is not None
            for sub, actions in plans:
                for action in actions:
                    try:
                        await self._execute(row, sub, action)
                    except Exception:
                        log.exception("Failed to deliver notification for subscription %s", sub.id)
                await self._sync_server_event(row, sub)
                if self.clock() > row.schedule.end_t + LIVE_MARGIN:
                    self.store.delete_records(sub.id)
            return outcome

    async def _fetch(self, row: ScheduleRow) -> FetchOutcome:
        now = self.clock()
        max_notice = max((s.notice for s in self.store.schedule_subscriptions(row.id)), default=0)
        try:
            result = await self.client.fetch_schedule(row.id, row.last_modified)
            schedule = parse_schedule(result.data) if result.data else row.schedule
        except (HoraroError, KeyError, ValueError, TypeError) as e:
            delay = next_fetch_delay(row.schedule, now, max_notice, row.failures + 1)
            self.store.mark_failed(row.id, next_fetch_at=now + delay)
            log.warning("Failed to fetch schedule %s (retry in %ss): %s", row.id, delay, e)
            return FetchOutcome.FAILED
        self.store.mark_fetched(
            row.id,
            payload=result.data,
            last_modified=result.last_modified,
            fetched_at=now,
            next_fetch_at=now + next_fetch_delay(schedule, now, max_notice, 0),
        )
        if result.data is not None and result.data != row.payload:
            log.info("Schedule %s was updated", row.id)
            return FetchOutcome.UPDATED
        return FetchOutcome.UNCHANGED

    def _plan_all(self, schedule_id: str) -> list[tuple[Subscription, list[Action]]]:
        row = self.store.get_schedule(schedule_id)
        assert row is not None
        schedule = row.schedule
        now = self.clock()
        result = []
        for sub in self.store.schedule_subscriptions(schedule_id):
            keys = item_keys(schedule, sub.key_column)
            actions = plan(schedule, keys, self.store.records(sub.id), now, sub.notice)
            result.append((sub, actions))
        return result

    async def _execute(self, row: ScheduleRow, sub: Subscription, action: Action) -> None:
        if isinstance(action, Send):
            kind = Kind.NOTICE if action.previous_t is None else Kind.RENOTICE
            notification = build_notification(
                kind, row, action.item, sub.key_column, action.previous_t
            )
            message_id = await self.discord.send(sub.channel_id, notification)
            t = action.item.scheduled_t
            record = Record(action.item_key, notification.title, t, t, sub.channel_id, message_id)
            self.store.save_record(sub.id, record)
            return

        record = action.record
        if record.message_id is not None:
            if action.item is None:
                notification = Notification(
                    kind=Kind.REMOVED,
                    schedule_name=display_name(row.event_name, row.schedule),
                    link=row.schedule.link,
                    title=record.title,
                    scheduled_t=record.notified_t,
                    previous_t=None,
                    length_t=None,
                    details=(),
                )
            elif action.item.scheduled_t == record.notified_t:
                notification = build_notification(
                    Kind.NOTICE, row, action.item, sub.key_column, None
                )
            else:
                notification = build_notification(
                    Kind.CHANGED, row, action.item, sub.key_column, record.notified_t
                )
            await self.discord.edit(record.channel_id, record.message_id, notification)
        if action.item is None:
            updated = replace(record, removed=True)
        else:
            updated = replace(record, displayed_t=action.item.scheduled_t, removed=False)
        self.store.save_record(sub.id, updated)

    async def _sync_server_event(self, row: ScheduleRow, sub: Subscription) -> None:
        if sub.server_event_id is None:
            return
        times = server_event_times(row.schedule)
        if self._synced_events.get(sub.server_event_id) == times:
            return
        self._synced_events[sub.server_event_id] = times
        try:
            exists = await self.discord.sync_server_event(sub.guild_id, sub.server_event_id, *times)
        except Exception:
            log.exception("Failed to update server event for subscription %s", sub.id)
            return
        if not exists:
            log.info("Server event of subscription %s was deleted; stop syncing", sub.id)
            self.store.update_subscription(replace(sub, server_event_id=None))
