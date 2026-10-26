"""Builders for Horaro API payloads, computed the same way Horaro does it."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

JST = timezone(timedelta(hours=9))
# 2026-10-10 12:00 JST
BASE_T = int(datetime(2026, 10, 10, 12, 0, tzinfo=JST).timestamp())

Row = tuple[str | None, str | None, int]  # (game, runner, length in minutes)


def at(hour: int, minute: int = 0, second: int = 0) -> int:
    """Unix time of the given JST time on the test day."""
    return int(datetime(2026, 10, 10, hour, minute, second, tzinfo=JST).timestamp())


def iso(t: int) -> str:
    return datetime.fromtimestamp(t, JST).isoformat()


def payload(
    rows: list[Row],
    *,
    start_t: int = BASE_T,
    setup_min: int = 0,
    schedule_id: str = "sched1",
    name: str = "Day 1",
    columns: tuple[str, ...] = ("Game", "Runner"),
) -> dict[str, Any]:
    items = []
    t = start_t
    for game, runner, minutes in rows:
        items.append(
            {
                "length": f"PT{minutes}M",
                "length_t": minutes * 60,
                "scheduled": iso(t),
                "scheduled_t": t,
                "data": [game, runner],
            }
        )
        t += (minutes + setup_min) * 60
    return {
        "id": schedule_id,
        "name": name,
        "slug": "day1",
        "timezone": "Asia/Tokyo",
        "start": iso(start_t),
        "start_t": start_t,
        "website": None,
        "twitter": None,
        "twitch": None,
        "bluesky": None,
        "description": None,
        "setup": f"PT{setup_min}M",
        "setup_t": setup_min * 60,
        "updated": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hidden_columns": [],
        "link": "https://horaro.net/testev/day1",
        "columns": list(columns),
        "items": items,
        "links": [
            {"rel": "self", "uri": f"https://horaro.net/-/api/v1/schedules/{schedule_id}"},
            {"rel": "event", "uri": "https://horaro.net/-/api/v1/events/ev1"},
        ],
    }


def rij_payload(
    rows: list[Row],
    *,
    start_t: int = BASE_T,
    setup_min: int = 0,
    event_id: str = "sched1",
) -> dict[str, Any]:
    return {
        "schemaVersion": 2,
        "event": {
            "id": event_id,
            "name": "RTA in Japan Winter 2026",
            "timezone": "Asia/Tokyo",
            "startsAt": iso(start_t),
        },
        "runs": [
            {
                "id": f"run-{i + 1:03}",
                "game": game or "",
                "category": "Any%",
                "platform": "PC",
                "runners": [{"name": runner}] if runner else [],
                "estimateSeconds": minutes * 60,
                "setupSeconds": setup_min * 60,
            }
            for i, (game, runner, minutes) in enumerate(rows)
        ],
    }
