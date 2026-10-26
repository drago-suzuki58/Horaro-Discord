"""Shared schedule models and payloads used by storage, notifications and views.

Horaro already provides this payload shape; other sources normalize to it at ingestion.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class ScheduleError(Exception):
    pass


class ScheduleNotFound(ScheduleError):
    pass


@dataclass(frozen=True)
class FetchResult:
    """`data` is None when the server answered 304 Not Modified."""

    data: dict[str, Any] | None
    last_modified: str | None


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
    """Read a stored payload (the same shape as a Horaro schedule's `data` object)."""
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
