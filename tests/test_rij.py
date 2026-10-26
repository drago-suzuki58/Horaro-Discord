from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from helpers import BASE_T, rij_payload

from horaro_discord.rij import RijClient, normalize_schedule, parse_url
from horaro_discord.schedule import ScheduleError, ScheduleNotFound, parse_schedule
from horaro_discord.timeline import item_keys, now_next


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("https://rtain.jp/schedule/?event=rtaijw2026", "rtaijw2026"),
        ("rtain.jp/schedule?event=rtaijw2026", "rtaijw2026"),
        (" https://rtain.jp/schedule/?event=rtaijw2026#run-002 ", "rtaijw2026"),
        ("https://rtain.jp/schedule/?other=x&event=rtaijex2", "rtaijex2"),
        ("https://rtain.jp/schedule/", None),
        ("https://rtain.jp/schedule/?event=", None),
        ("https://rtain.jp/schedule/?event=a&event=b", None),
        ("https://rtain.jp/schedule/?event=..%2Fsecret", None),
        ("https://rtain.jp/schedule/data/rtaijw2026.json", None),
        ("https://rtain.jp/other/?event=rtaijw2026", None),
        ("https://rtain.jp.example.com/schedule/?event=rtaijw2026", None),
        ("https://other.com/schedule/?event=rtaijw2026", None),
        ("https://user@rtain.jp/schedule/?event=rtaijw2026", None),
        ("https://rtain.jp:8080/schedule/?event=rtaijw2026", None),
        ("https://rtain.jp:bad/schedule/?event=rtaijw2026", None),
        ("https://[invalid/schedule/?event=a", None),
        ("ftp://rtain.jp/schedule/?event=rtaijw2026", None),
    ],
)
def test_parse_url(text: str, expected: str | None) -> None:
    assert parse_url(text) == expected


def test_normalize_schedule() -> None:
    body = rij_payload([("Alpha", "ann", 30), ("Beta", "bob", 15)], setup_min=8)
    body["runs"][0]["runners"].append({"name": "cid", "team": "A", "twitch": "https://x.test"})
    body["runs"][0]["commentators"] = [{"name": "dan"}]
    schedule = parse_schedule(normalize_schedule(body))
    assert schedule.id == "rij:sched1"
    assert schedule.name == "RTA in Japan Winter 2026"
    assert schedule.link == "https://rtain.jp/schedule/?event=sched1"
    assert schedule.timezone == "Asia/Tokyo"
    assert schedule.columns == ("ゲーム", "カテゴリ", "機種", "走者", "解説")
    first, second = schedule.items
    assert schedule.start_t == first.scheduled_t == BASE_T
    assert first.end_t == BASE_T + 30 * 60
    assert second.scheduled_t == BASE_T + 38 * 60
    assert schedule.end_t == BASE_T + 53 * 60  # Excludes the final setup, like the page.
    assert first.values == ("Alpha", "Any%", "PC", "ann\ncid", "dan")
    assert schedule.value(second, "解説") == ""
    assert now_next(schedule, first.end_t).current is None


def test_normalize_empty_schedule() -> None:
    schedule = parse_schedule(normalize_schedule(rij_payload([])))
    assert schedule.items == ()
    assert schedule.end_t == BASE_T


def test_identity_does_not_depend_on_run_ids_or_runners() -> None:
    body = rij_payload([("Alpha", "ann", 30), ("Alpha", "bob", 15)])
    keys = item_keys(parse_schedule(normalize_schedule(body)), "ゲーム")
    body["runs"][0]["id"] = "changed"
    body["runs"][0]["runners"] = [{"name": "other"}]
    assert item_keys(parse_schedule(normalize_schedule(body)), "ゲーム") == keys
    assert keys == ["k:alpha#0", "k:alpha#1"]


@pytest.mark.parametrize("field", ["estimateSeconds", "setupSeconds"])
@pytest.mark.parametrize("value", [-1, 1.5, "30", None, True])
def test_invalid_durations(field: str, value: Any) -> None:
    body = rij_payload([("Alpha", "ann", 30)])
    body["runs"][0][field] = value
    with pytest.raises(ValueError):
        normalize_schedule(body)


def test_start_time_requires_timezone() -> None:
    body = rij_payload([])
    body["event"]["startsAt"] = "2026-12-25T15:00:00"
    with pytest.raises(ValueError, match="timezone"):
        normalize_schedule(body)


class FakeRij:
    def __init__(self) -> None:
        self.data = rij_payload([("Alpha", "ann", 30)])
        self.events: Any = [
            {"id": "sched1", "name": "RTA in Japan Winter 2026", "scheduleFile": "sched1.json"},
            {"id": "older", "name": "RTA in Japan Summer 2025", "scheduleFile": "older.json"},
        ]
        self.status = 200
        self.html = False
        self.slow = False
        self.requests: list[web.Request] = []
        self.last_modified = "Sun, 25 Oct 2026 11:20:30 GMT"

    async def handle(self, request: web.Request) -> web.StreamResponse:
        self.requests.append(request)
        if self.slow:
            await asyncio.sleep(0.1)
        if self.status != 200 or self.html:
            return web.Response(status=self.status, text="<html>Error</html>")
        if request.headers.get("If-Modified-Since") == self.last_modified:
            return web.Response(status=304)
        data = (
            {"schemaVersion": 2, "events": self.events}
            if request.match_info["file"] == "events.json"
            else self.data
        )
        return web.json_response(data, headers={"Last-Modified": self.last_modified})


@pytest.fixture
async def rij() -> AsyncIterator[tuple[FakeRij, RijClient]]:
    fake = FakeRij()
    app = web.Application()
    app.router.add_get("/schedule/data/{file}", fake.handle)
    async with TestServer(app) as server, aiohttp.ClientSession() as session:
        yield fake, RijClient(session, str(server.make_url("/schedule")))


async def test_fetch_schedule(rij: tuple[FakeRij, RijClient]) -> None:
    fake, client = rij
    result = await client.fetch_schedule("sched1")
    assert result.data == normalize_schedule(fake.data)
    assert result.last_modified == fake.last_modified
    assert fake.requests[0].path == "/schedule/data/sched1.json"
    assert "_" in fake.requests[0].query
    assert "Horaro-Discord" in fake.requests[0].headers["User-Agent"]


async def test_not_modified(rij: tuple[FakeRij, RijClient]) -> None:
    fake, client = rij
    result = await client.fetch_schedule("sched1", fake.last_modified)
    assert result.data is None


@pytest.mark.parametrize("status", [404, 410, 500])
async def test_http_errors(rij: tuple[FakeRij, RijClient], status: int) -> None:
    fake, client = rij
    fake.status = status
    error = ScheduleNotFound if status == 404 else ScheduleError
    with pytest.raises(error):
        await client.fetch_schedule("sched1")


async def test_html_instead_of_json(rij: tuple[FakeRij, RijClient]) -> None:
    fake, client = rij
    fake.html = True
    with pytest.raises(ScheduleError):
        await client.fetch_schedule("sched1")


@pytest.mark.parametrize("version", [1, 3, None])
async def test_unsupported_schema(rij: tuple[FakeRij, RijClient], version: Any) -> None:
    fake, client = rij
    fake.data["schemaVersion"] = version
    with pytest.raises(ScheduleError, match="schema"):
        await client.fetch_schedule("sched1")


@pytest.mark.parametrize("field", ["event", "runs"])
async def test_missing_data(rij: tuple[FakeRij, RijClient], field: str) -> None:
    fake, client = rij
    del fake.data[field]
    with pytest.raises(ScheduleError):
        await client.fetch_schedule("sched1")


async def test_mismatching_event_id(rij: tuple[FakeRij, RijClient]) -> None:
    fake, client = rij
    fake.data["event"]["id"] = "other"
    with pytest.raises(ScheduleError, match="does not match"):
        await client.fetch_schedule("sched1")


async def test_invalid_event_id_is_not_requested(rij: tuple[FakeRij, RijClient]) -> None:
    fake, client = rij
    with pytest.raises(ScheduleError):
        await client.fetch_schedule("../secret")
    assert fake.requests == []


async def test_search_events(rij: tuple[FakeRij, RijClient]) -> None:
    _, client = rij
    assert await client.search_events("winter", timeout=1) == [
        {"name": "RTA in Japan Winter 2026", "link": "https://rtain.jp/schedule/?event=sched1"}
    ]
    assert await client.search_events("missing", timeout=1) == []


async def test_invalid_event_list(rij: tuple[FakeRij, RijClient]) -> None:
    fake, client = rij
    fake.events = None
    with pytest.raises(ScheduleError):
        await client.search_events("winter", timeout=1)


async def test_timeout(rij: tuple[FakeRij, RijClient]) -> None:
    fake, client = rij
    fake.slow = True
    with pytest.raises(ScheduleError):
        await client.search_events("winter", timeout=0.01)
