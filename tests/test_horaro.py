from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from helpers import BASE_T, payload

from horaro_discord.horaro import (
    HoraroClient,
    HoraroRef,
    event_api_url,
    parse_url,
)
from horaro_discord.schedule import ScheduleError, ScheduleNotFound, parse_schedule


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("https://horaro.net/esa/2026-winter1", HoraroRef("esa", "2026-winter1")),
        ("https://horaro.org/esa/2026-winter1", HoraroRef("esa", "2026-winter1")),
        ("horaro.net/esa/2026-winter1/", HoraroRef("esa", "2026-winter1")),
        ("https://www.horaro.org/esa/2026-winter1.json?key=x", HoraroRef("esa", "2026-winter1")),
        ("  https://horaro.net/esa  ", HoraroRef("esa", None)),
        ("https://example.com/esa/2026", None),
        ("https://horaro.net/", None),
        ("https://horaro.net/-/api/v1", None),
        ("https://horaro.net/a/b/c", None),
        ("https://[invalid/a/b", None),
        ("esa", None),
    ],
)
def test_parse_url(text: str, expected: HoraroRef | None) -> None:
    assert parse_url(text) == expected


def test_parse_schedule() -> None:
    data = payload([("Alpha", "[ann](https://twitch.tv/ann)", 30), (None, "Break", 15)])
    # Hidden columns are removed by the API and items may carry options.
    data["items"][0]["options"] = {"setup": "10m"}
    schedule = parse_schedule(data)
    assert schedule.id == "sched1"
    assert schedule.columns == ("Game", "Runner")
    assert schedule.start_t == BASE_T
    assert schedule.end_t == BASE_T + 45 * 60
    first, second = schedule.items
    assert first.values == ("Alpha", "[ann](https://twitch.tv/ann)")
    assert schedule.value(second, "Game") is None
    assert schedule.value(second, "Missing") is None
    assert event_api_url(data) == "https://horaro.net/-/api/v1/events/ev1"


def test_parse_empty_schedule() -> None:
    schedule = parse_schedule(payload([]))
    assert schedule.items == ()
    assert schedule.end_t == schedule.start_t


class FakeHoraro:
    def __init__(self) -> None:
        self.data = payload([("Alpha", "ann", 30)])
        self.last_modified = "Wed, 02 Sep 2026 00:38:53 GMT"
        self.requests: list[web.Request] = []

    def app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/-/api/v1/schedules/{id}", self.schedule)
        app.router.add_get("/-/api/v1/events/{e}/schedules/{s}", self.redirect)
        app.router.add_get("/-/api/v1/events", self.events)
        app.router.add_get("/-/api/v1/error", self.error)
        app.router.add_get("/-/api/v1/slow", self.slow)
        return app

    async def schedule(self, request: web.Request) -> web.StreamResponse:
        self.requests.append(request)
        if request.match_info["id"] != "sched1":
            return web.Response(status=404, text="<html>Not Found</html>", content_type="text/html")
        if request.headers.get("If-Modified-Since") == self.last_modified:
            return web.Response(status=304)
        return web.json_response({"data": self.data}, headers={"Last-Modified": self.last_modified})

    async def redirect(self, request: web.Request) -> web.StreamResponse:
        raise web.HTTPFound("/-/api/v1/schedules/sched1")

    async def events(self, request: web.Request) -> web.StreamResponse:
        self.requests.append(request)
        return web.json_response({"data": [{"name": "Test Event", "link": "x"}]})

    async def error(self, request: web.Request) -> web.StreamResponse:
        return web.Response(status=500, text="<html>Error</html>", content_type="text/html")

    async def slow(self, request: web.Request) -> web.StreamResponse:
        await asyncio.sleep(1)
        return web.json_response({"data": {}})


@pytest.fixture
async def horaro() -> AsyncIterator[tuple[FakeHoraro, HoraroClient]]:
    fake = FakeHoraro()
    server = TestServer(fake.app())
    await server.start_server()
    async with aiohttp.ClientSession() as session:
        yield fake, HoraroClient(session, str(server.make_url("")))
    await server.close()


async def test_fetch_schedule(horaro: tuple[FakeHoraro, HoraroClient]) -> None:
    fake, client = horaro
    result = await client.fetch_schedule("sched1", None)
    assert result.data == fake.data
    assert result.last_modified == fake.last_modified
    assert "Horaro-Discord" in fake.requests[0].headers["User-Agent"]


async def test_fetch_schedule_not_modified(horaro: tuple[FakeHoraro, HoraroClient]) -> None:
    fake, client = horaro
    result = await client.fetch_schedule("sched1", fake.last_modified)
    assert result.data is None


async def test_fetch_schedule_by_slug_follows_redirect(
    horaro: tuple[FakeHoraro, HoraroClient],
) -> None:
    fake, client = horaro
    result = await client.fetch_schedule_by_slug("testev", "day1")
    assert result.data is not None
    assert result.data["id"] == "sched1"


async def test_not_found_html(horaro: tuple[FakeHoraro, HoraroClient]) -> None:
    _, client = horaro
    with pytest.raises(ScheduleNotFound):
        await client.fetch_schedule("missing", None)


async def test_server_error_html(horaro: tuple[FakeHoraro, HoraroClient]) -> None:
    _, client = horaro
    with pytest.raises(ScheduleError, match="HTTP 500"):
        await client.fetch_event("/-/api/v1/error")


async def test_timeout(horaro: tuple[FakeHoraro, HoraroClient]) -> None:
    _, client = horaro
    with pytest.raises(ScheduleError):
        await client._get("/-/api/v1/slow", timeout=0.1)


async def test_search_events_uses_max(horaro: tuple[FakeHoraro, HoraroClient]) -> None:
    fake, client = horaro
    events: list[dict[str, Any]] = await client.search_events("test", timeout=5)
    assert events[0]["name"] == "Test Event"
    assert fake.requests[0].query["max"] == "25"
    assert fake.requests[0].query["name"] == "test"
