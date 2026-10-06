"""Replays an event with a fake clock, a fake Horaro server and a fake Discord."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from helpers import Row, at, payload

from horaro_discord.horaro import HoraroClient
from horaro_discord.scheduler import TICK_INTERVAL, Kind, Notification, Scheduler
from horaro_discord.store import Store

ROWS: list[Row] = [("Alpha", "ann", 30), ("Beta", "bob", 30), ("Gamma", "cid", 30)]


class FakeHoraro:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self.version = 1
        self.failing = False
        self.requests: list[int] = []
        self.clock: Callable[[], int] = lambda: 0

    def update(self, rows: list[Row]) -> None:
        self.data = payload(rows)
        self.version += 1

    async def handle(self, request: web.Request) -> web.StreamResponse:
        self.requests.append(self.clock())
        if self.failing:
            return web.Response(status=503, text="<html>down</html>", content_type="text/html")
        last_modified = f"v{self.version}"
        if request.headers.get("If-Modified-Since") == last_modified:
            return web.Response(status=304)
        return web.json_response({"data": self.data}, headers={"Last-Modified": last_modified})


@dataclass
class FakeDiscord:
    clock: Callable[[], int]
    sent: list[tuple[int, int, Notification]] = field(default_factory=list)
    edited: list[tuple[int, int, int, Notification]] = field(default_factory=list)
    synced: list[tuple[int, int, int]] = field(default_factory=list)
    event_exists: bool = True

    async def send(self, channel_id: int, notification: Notification) -> int | None:
        message_id = 1000 + len(self.sent)
        self.sent.append((self.clock(), channel_id, notification))
        return message_id

    async def edit(self, channel_id: int, message_id: int, notification: Notification) -> None:
        self.edited.append((self.clock(), channel_id, message_id, notification))

    async def sync_server_event(
        self, guild_id: int, event_id: int, start_t: int, end_t: int
    ) -> bool:
        self.synced.append((event_id, start_t, end_t))
        return self.event_exists


class Sim:
    def __init__(self, horaro: FakeHoraro, client: HoraroClient, start: int) -> None:
        self.now = start
        self.horaro = horaro
        horaro.clock = self.clock
        self.client = client
        self.store = Store(":memory:")
        self.discord = FakeDiscord(self.clock)
        self.scheduler = self.new_scheduler()
        self.store.save_schedule(
            horaro.data, event_name="Test Event", last_modified=None, fetched_at=0, next_fetch_at=0
        )

    def clock(self) -> int:
        return self.now

    def new_scheduler(self) -> Scheduler:
        return Scheduler(self.store, self.client, self.discord, self.clock)

    def subscribe(self, guild_id: int = 1, notice_minutes: int = 10) -> int:
        sub = self.store.add_subscription(
            guild_id=guild_id,
            channel_id=guild_id * 10,
            schedule_id="sched1",
            notice_minutes=notice_minutes,
            key_column="Game",
        )
        return sub.id

    async def run_until(self, t: int) -> None:
        while self.now < t:
            await self.scheduler.tick()
            self.now += TICK_INTERVAL

    def sent(self) -> list[tuple[int, str, Kind, int, int | None]]:
        return [(t, n.title, n.kind, n.scheduled_t, n.previous_t) for t, _, n in self.discord.sent]

    def edited(self) -> list[tuple[int, int, str, Kind, int, int | None]]:
        return [
            (t, mid, n.title, n.kind, n.scheduled_t, n.previous_t)
            for t, _, mid, n in self.discord.edited
        ]


@pytest.fixture
async def sim() -> AsyncIterator[Sim]:
    horaro = FakeHoraro(payload(ROWS))
    app = web.Application()
    app.router.add_get("/-/api/v1/schedules/{id}", horaro.handle)
    server = TestServer(app)
    await server.start_server()
    async with aiohttp.ClientSession() as session:
        yield Sim(horaro, HoraroClient(session, str(server.make_url(""))), at(11, 0))
    await server.close()


async def test_notifications_follow_the_schedule(sim: Sim) -> None:
    sim.subscribe()
    await sim.run_until(at(14, 0))
    assert sim.sent() == [
        (at(11, 50), "Alpha", Kind.NOTICE, at(12, 0), None),
        (at(12, 20), "Beta", Kind.NOTICE, at(12, 30), None),
        (at(12, 50), "Gamma", Kind.NOTICE, at(13, 0), None),
    ]
    assert sim.edited() == []


async def test_delay_during_event_moves_later_notifications(sim: Sim) -> None:
    """The bug of the old bot: a change during the event was not picked up."""
    sim.subscribe()
    await sim.run_until(at(12, 15))
    sim.horaro.update([("Alpha", "ann", 50), ("Beta", "bob", 30), ("Gamma", "cid", 30)])
    await sim.run_until(at(14, 0))
    assert sim.sent() == [
        (at(11, 50), "Alpha", Kind.NOTICE, at(12, 0), None),
        (at(12, 40), "Beta", Kind.NOTICE, at(12, 50), None),
        (at(13, 10), "Gamma", Kind.NOTICE, at(13, 20), None),
    ]


async def test_delay_after_notification_edits_and_renotifies(sim: Sim) -> None:
    sim.subscribe()
    await sim.run_until(at(12, 22))
    sim.horaro.update([("Alpha", "ann", 50), ("Beta", "bob", 30), ("Gamma", "cid", 30)])
    await sim.run_until(at(14, 0))

    beta_message = 1001
    [(edited_at, message_id, title, kind, new_t, old_t)] = sim.edited()
    assert at(12, 22) <= edited_at <= at(12, 23) + TICK_INTERVAL
    assert (message_id, title, kind, new_t, old_t) == (
        beta_message,
        "Beta",
        Kind.CHANGED,
        at(12, 50),
        at(12, 30),
    )
    assert sim.sent()[1:] == [
        (at(12, 20), "Beta", Kind.NOTICE, at(12, 30), None),
        (at(12, 40), "Beta", Kind.RENOTICE, at(12, 50), at(12, 30)),
        (at(13, 10), "Gamma", Kind.NOTICE, at(13, 20), None),
    ]


async def test_small_shift_after_notification_only_edits(sim: Sim) -> None:
    sim.subscribe()
    await sim.run_until(at(12, 22))
    sim.horaro.update([("Alpha", "ann", 33), ("Beta", "bob", 30), ("Gamma", "cid", 30)])
    await sim.run_until(at(12, 40))
    assert [e[2:] for e in sim.edited()] == [("Beta", Kind.CHANGED, at(12, 33), at(12, 30))]
    assert [s[1] for s in sim.sent()] == ["Alpha", "Beta"]


async def test_runner_swap_does_not_renotify(sim: Sim) -> None:
    sim.subscribe()
    await sim.run_until(at(12, 22))
    sim.horaro.update([("Alpha", "ann", 30), ("Beta", "someone else", 30), ("Gamma", "cid", 30)])
    await sim.run_until(at(12, 40))
    assert sim.edited() == []
    assert [s[1] for s in sim.sent()] == ["Alpha", "Beta"]


async def test_removed_item_message_is_marked(sim: Sim) -> None:
    sim.subscribe()
    await sim.run_until(at(12, 52))
    sim.horaro.update([("Alpha", "ann", 30), ("Beta", "bob", 30)])
    await sim.run_until(at(14, 0))
    assert [e[1:] for e in sim.edited()] == [(1002, "Gamma", Kind.REMOVED, at(13, 0), None)]


async def test_restart_does_not_resend(sim: Sim) -> None:
    sim.subscribe()
    await sim.run_until(at(12, 25))
    sim.scheduler = sim.new_scheduler()
    await sim.run_until(at(12, 45))
    assert [s[1] for s in sim.sent()] == ["Alpha", "Beta"]


async def test_stale_data_is_refreshed_before_sending(sim: Sim) -> None:
    sim.subscribe()
    await sim.run_until(at(11, 40))
    # Pretend the last fetch was long ago and the next one is far away.
    sim.store.mark_fetched(
        "sched1", payload=None, last_modified=None, fetched_at=at(11, 0), next_fetch_at=at(13, 0)
    )
    sim.horaro.update([("Alpha", "ann", 30)])
    sim.horaro.data = payload([("Alpha", "ann", 30)], start_t=at(12, 30))
    await sim.run_until(at(11, 51))
    assert sim.sent() == []


async def test_horaro_outage_uses_cached_schedule(sim: Sim) -> None:
    sim.subscribe()
    await sim.run_until(at(11, 30))
    sim.horaro.failing = True
    before = len(sim.horaro.requests)
    await sim.run_until(at(14, 0))
    assert [s[1] for s in sim.sent()] == ["Alpha", "Beta", "Gamma"]
    # Retries back off instead of hitting Horaro every tick.
    assert len(sim.horaro.requests) - before < 20


async def test_fetch_interval_depends_on_phase(sim: Sim) -> None:
    sim.subscribe()
    await sim.run_until(at(11, 20))
    idle = len(sim.horaro.requests)
    await sim.run_until(at(12, 20))
    live = len(sim.horaro.requests) - idle
    assert idle <= 2
    assert 55 <= live <= 61


async def test_shared_schedule_is_fetched_once(sim: Sim) -> None:
    sim.subscribe(guild_id=1)
    sim.subscribe(guild_id=2, notice_minutes=5)
    await sim.run_until(at(11, 30))
    sim.horaro.requests.clear()
    await sim.run_until(at(12, 10))
    assert len(sim.horaro.requests) <= 41
    assert [(s[1], s[0]) for s in sim.sent()] == [("Alpha", at(11, 50)), ("Alpha", at(11, 55))]
    assert {channel for _, channel, _ in sim.discord.sent} == {10, 20}


async def test_server_event_follows_schedule(sim: Sim) -> None:
    sub_id = sim.subscribe()
    sub = sim.store.get_subscription(1, "sched1")
    assert sub is not None
    from dataclasses import replace

    sim.store.update_subscription(replace(sub, server_event_id=99))
    await sim.run_until(at(12, 15))
    assert sim.discord.synced == [(99, at(12, 0), at(13, 30))]

    sim.horaro.update([("Alpha", "ann", 50), ("Beta", "bob", 30), ("Gamma", "cid", 30)])
    sim.discord.event_exists = False
    await sim.run_until(at(12, 20))
    assert sim.discord.synced[1:] == [(99, at(12, 0), at(13, 50))]
    # The event was deleted in Discord, so syncing stops.
    updated = sim.store.get_subscription(1, "sched1")
    assert updated is not None and updated.id == sub_id
    assert updated.server_event_id is None


async def test_records_are_pruned_after_the_schedule_ends(sim: Sim) -> None:
    sub_id = sim.subscribe()
    await sim.run_until(at(13, 0) + TICK_INTERVAL)
    assert len(sim.store.records(sub_id)) == 3
    await sim.run_until(at(14, 30))
    assert sim.store.records(sub_id) == {}
