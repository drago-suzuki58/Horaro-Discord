"""RTA in Japan's public schedule JSON (schema version 2).

Times are derived exactly as on the official page: each run's estimate and setup
advance the next start, but setup is not part of the run's playing time.
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

import aiohttp

from .horaro import USER_AGENT
from .schedule import FetchResult, ScheduleError, ScheduleNotFound

BASE_URL = "https://rtain.jp/schedule"
ID_PREFIX = "rij:"
_EVENT_ID = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")


def parse_url(text: str) -> str | None:
    """Return the event ID only for an official schedule page URL."""
    text = text.strip()
    if "://" not in text:
        text = "https://" + text
    try:
        parts = urlsplit(text)
        if (
            parts.scheme not in {"http", "https"}
            or parts.hostname != "rtain.jp"
            or parts.username is not None
            or parts.password is not None
            or parts.port not in {None, 80, 443}
            or parts.path.rstrip("/") != "/schedule"
        ):
            return None
        events = parse_qs(parts.query, keep_blank_values=True).get("event", [])
        if len(events) == 1 and _EVENT_ID.fullmatch(events[0]):
            return events[0]
    except ValueError:
        pass
    return None


def event_url(event_id: str) -> str:
    return f"{BASE_URL}/?event={event_id}"


def _text(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("Expected a string")
    return value


def _names(people: Any) -> str:
    if not isinstance(people, list):
        raise ValueError("Expected a list of people")
    return "\n".join(_text(person["name"]) for person in people)


def normalize_schedule(body: dict[str, Any]) -> dict[str, Any]:
    """Convert to the existing stored payload without relying on run ID stability."""
    if body["schemaVersion"] != 2:
        raise ValueError("Unsupported RiJ schema version")
    event = body["event"]
    event_id = _text(event["id"])
    if not _EVENT_ID.fullmatch(event_id):
        raise ValueError("Invalid RiJ event ID")
    start = datetime.fromisoformat(_text(event["startsAt"]))
    if start.tzinfo is None:
        raise ValueError("RiJ start time must include a timezone")
    start_t = int(start.timestamp())
    t = start_t
    items = []
    if not isinstance(body["runs"], list):
        raise ValueError("Expected a list of runs")
    for run in body["runs"]:
        length, setup = run["estimateSeconds"], run["setupSeconds"]
        if type(length) is not int or type(setup) is not int or min(length, setup) < 0:
            raise ValueError("Run and setup durations must be nonnegative integer seconds")
        items.append(
            {
                "scheduled_t": t,
                "length_t": length,
                "data": [
                    _text(run["game"]),
                    _text(run["category"]),
                    _text(run["platform"]),
                    _names(run["runners"]),
                    _names(run.get("commentators", [])),
                ],
            }
        )
        t += length + setup
    return {
        "id": ID_PREFIX + event_id,
        "name": _text(event["name"]),
        "link": event_url(event_id),
        "timezone": _text(event["timezone"]),
        "start": start.isoformat(),
        "start_t": start_t,
        "columns": ["ゲーム", "カテゴリ", "機種", "走者", "解説"],
        "items": items,
    }


class RijClient:
    def __init__(self, session: aiohttp.ClientSession, base_url: str = BASE_URL) -> None:
        self._session = session
        self._base = base_url.rstrip("/")

    async def _get(
        self, filename: str, if_modified_since: str | None = None, *, timeout: float = 15
    ) -> FetchResult:
        url = f"{self._base}/data/{filename}"
        headers = {"User-Agent": USER_AGENT}
        if if_modified_since:
            headers["If-Modified-Since"] = if_modified_since
        try:
            async with self._session.get(
                url,
                # The official page also cache-busts its static JSON requests.
                params={"_": str(time.time_ns() // 1_000_000)},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status == 304:
                    return FetchResult(None, resp.headers.get("Last-Modified"))
                if resp.status == 404:
                    raise ScheduleNotFound(url)
                if resp.status != 200 or resp.content_type != "application/json":
                    raise ScheduleError(f"{url}: HTTP {resp.status} ({resp.content_type})")
                body = await resp.json()
                if not isinstance(body, dict) or body.get("schemaVersion") != 2:
                    raise ScheduleError(f"{url}: unsupported RiJ schema")
                return FetchResult(body, resp.headers.get("Last-Modified"))
        except (aiohttp.ClientError, TimeoutError, ValueError) as e:
            raise ScheduleError(f"{url}: {e!r}") from e

    async def fetch_schedule(
        self, event_id: str, if_modified_since: str | None = None
    ) -> FetchResult:
        if not _EVENT_ID.fullmatch(event_id):
            raise ScheduleError("Invalid RiJ event ID")
        result = await self._get(f"{event_id}.json", if_modified_since)
        if result.data is None:
            return result
        try:
            payload = normalize_schedule(result.data)
            if payload["id"] != ID_PREFIX + event_id:
                raise ValueError("RiJ event ID does not match the requested event")
        except (KeyError, ValueError, TypeError, AttributeError, OverflowError) as e:
            raise ScheduleError(f"Invalid RiJ schedule: {e!r}") from e
        return FetchResult(payload, result.last_modified)

    async def search_events(self, name: str, timeout: float) -> list[dict[str, Any]]:
        result = await self._get("events.json", timeout=timeout)
        try:
            assert result.data is not None
            events = result.data["events"]
            if not isinstance(events, list):
                raise ValueError("Expected a list of events")
            return [
                {"name": _text(event["name"]), "link": event_url(event["id"])}
                for event in events
                if _EVENT_ID.fullmatch(_text(event["id"]))
                and name.casefold() in _text(event["name"]).casefold()
            ][:25]
        except (KeyError, ValueError, TypeError) as e:
            raise ScheduleError(f"Invalid RiJ event list: {e!r}") from e
