"""Horaro API client and schedule models.

API docs: https://horaro.net/-/api
horaro.org became a static archive in 2026, so horaro.org URLs are read as horaro.net.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import aiohttp

BASE_URL = "https://horaro.net"
USER_AGENT = "Horaro-Discord (+https://github.com/drago-suzuki58/Horaro-Discord)"
_HOSTS = {"horaro.net", "www.horaro.net", "horaro.org", "www.horaro.org"}
_SLUG = re.compile(r"^[A-Za-z0-9_-]+$")
_EXPORT_SUFFIX = re.compile(r"\.(json|jsonp|xml|csv|ical)$")


class HoraroError(Exception):
    pass


class HoraroNotFound(HoraroError):
    pass


@dataclass(frozen=True)
class HoraroRef:
    """Position in a Horaro URL. `schedule` is None for event URLs."""

    event: str
    schedule: str | None


def parse_url(text: str) -> HoraroRef | None:
    text = text.strip()
    if "://" not in text:
        text = "https://" + text
    parts = urlsplit(text)
    if parts.hostname not in _HOSTS:
        return None
    segments = [s for s in parts.path.split("/") if s]
    if segments:
        segments[-1] = _EXPORT_SUFFIX.sub("", segments[-1])
    if not 1 <= len(segments) <= 2 or segments[0] == "-":
        return None
    if not all(_SLUG.match(s) for s in segments):
        return None
    return HoraroRef(segments[0], segments[1] if len(segments) == 2 else None)


@dataclass(frozen=True)
class Item:
    index: int
    scheduled_t: int
    length_t: int
    values: tuple[str | None, ...]

    @property
    def end_t(self) -> int:
        return self.scheduled_t + self.length_t


@dataclass(frozen=True)
class Schedule:
    id: str
    name: str
    link: str
    timezone: str
    start_t: int
    columns: tuple[str, ...]
    items: tuple[Item, ...]

    @property
    def end_t(self) -> int:
        return self.items[-1].end_t if self.items else self.start_t

    def value(self, item: Item, column: str) -> str | None:
        try:
            return item.values[self.columns.index(column)]
        except (ValueError, IndexError):
            return None


def parse_schedule(data: dict[str, Any]) -> Schedule:
    """Build a Schedule from the `data` object of /-/api/v1/schedules/{id}."""
    columns = tuple(str(c) for c in data["columns"])
    items = tuple(
        Item(
            index=i,
            scheduled_t=int(raw["scheduled_t"]),
            length_t=int(raw["length_t"]),
            values=tuple(None if v is None else str(v) for v in raw["data"]),
        )
        for i, raw in enumerate(data["items"])
    )
    return Schedule(
        id=str(data["id"]),
        name=str(data["name"]),
        link=str(data["link"]),
        timezone=str(data["timezone"]),
        start_t=int(data["start_t"]),
        columns=columns,
        items=items,
    )


def event_api_url(data: dict[str, Any]) -> str | None:
    for link in data.get("links", []):
        if link.get("rel") == "event":
            return str(link["uri"])
    return None


@dataclass(frozen=True)
class FetchResult:
    """`data` is None when the server answered 304 Not Modified."""

    data: dict[str, Any] | None
    last_modified: str | None


class HoraroClient:
    def __init__(self, session: aiohttp.ClientSession, base_url: str = BASE_URL) -> None:
        self._session = session
        self._base = base_url.rstrip("/")

    async def _get(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 15,
    ) -> FetchResult:
        if url.startswith("/"):
            url = self._base + url
        try:
            async with self._session.get(
                url,
                params=params,
                headers={"User-Agent": USER_AGENT, **(headers or {})},
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status == 304:
                    return FetchResult(None, resp.headers.get("Last-Modified"))
                if resp.status == 404:
                    raise HoraroNotFound(url)
                # Errors come back as HTML pages, so check before parsing JSON.
                if resp.status != 200 or resp.content_type != "application/json":
                    raise HoraroError(f"{url}: HTTP {resp.status} ({resp.content_type})")
                body = await resp.json()
                return FetchResult(body["data"], resp.headers.get("Last-Modified"))
        except (aiohttp.ClientError, TimeoutError, ValueError, KeyError) as e:
            raise HoraroError(f"{url}: {e!r}") from e

    async def fetch_schedule(self, schedule_id: str, if_modified_since: str | None) -> FetchResult:
        headers = {"If-Modified-Since": if_modified_since} if if_modified_since else None
        return await self._get(f"/-/api/v1/schedules/{schedule_id}", headers=headers)

    async def fetch_schedule_by_slug(self, event: str, schedule: str) -> FetchResult:
        # Redirects to /-/api/v1/schedules/{id}.
        return await self._get(f"/-/api/v1/events/{event}/schedules/{schedule}")

    async def fetch_event(self, url: str) -> dict[str, Any]:
        data = (await self._get(url)).data
        assert data is not None
        return data

    async def list_event_schedules(self, event: str) -> list[dict[str, Any]]:
        """Schedules of an event, including all items. Slow for large events."""
        data = (await self._get(f"/-/api/v1/events/{event}/schedules", timeout=30)).data
        assert isinstance(data, list)
        return data

    async def search_events(self, name: str, timeout: float) -> list[dict[str, Any]]:
        params = {"name": name, "max": "25"}
        data = (await self._get("/-/api/v1/events", params=params, timeout=timeout)).data
        assert isinstance(data, list)
        return data
