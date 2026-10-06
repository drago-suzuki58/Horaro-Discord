"""SQLite storage. Every query that changes a subscription is scoped by its row or guild."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .horaro import Schedule, parse_schedule
from .timeline import Record

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE schedules (
    id TEXT PRIMARY KEY,
    event_name TEXT NOT NULL,
    payload TEXT NOT NULL,
    last_modified TEXT,
    fetched_at INTEGER NOT NULL,
    next_fetch_at INTEGER NOT NULL,
    failures INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE subscriptions (
    id INTEGER PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    schedule_id TEXT NOT NULL REFERENCES schedules (id),
    notice_minutes INTEGER NOT NULL,
    key_column TEXT,
    server_event_id INTEGER,
    UNIQUE (guild_id, schedule_id)
);
CREATE TABLE notifications (
    subscription_id INTEGER NOT NULL REFERENCES subscriptions (id) ON DELETE CASCADE,
    item_key TEXT NOT NULL,
    title TEXT NOT NULL,
    notified_t INTEGER NOT NULL,
    displayed_t INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    message_id INTEGER,
    removed INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (subscription_id, item_key)
);
"""


@dataclass(frozen=True)
class ScheduleRow:
    id: str
    event_name: str
    payload: dict[str, Any]
    last_modified: str | None
    fetched_at: int
    next_fetch_at: int
    failures: int

    @property
    def schedule(self) -> Schedule:
        return parse_schedule(self.payload)


@dataclass(frozen=True)
class Subscription:
    id: int
    guild_id: int
    channel_id: int
    schedule_id: str
    notice_minutes: int
    key_column: str | None
    server_event_id: int | None

    @property
    def notice(self) -> int:
        return self.notice_minutes * 60


class Store:
    def __init__(self, path: str | Path) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        version = self._db.execute("PRAGMA user_version").fetchone()[0]
        if version == 0:
            with self._db:
                self._db.executescript(_SCHEMA)
                self._db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        elif version != SCHEMA_VERSION:
            raise RuntimeError(f"Unsupported database schema version: {version}")

    def close(self) -> None:
        self._db.close()

    # schedules

    def save_schedule(
        self,
        payload: dict[str, Any],
        *,
        event_name: str,
        last_modified: str | None,
        fetched_at: int,
        next_fetch_at: int,
    ) -> None:
        with self._db:
            self._db.execute(
                """
                INSERT INTO schedules
                    (id, event_name, payload, last_modified, fetched_at, next_fetch_at, failures)
                VALUES (?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT (id) DO UPDATE SET
                    event_name = excluded.event_name, payload = excluded.payload,
                    last_modified = excluded.last_modified, fetched_at = excluded.fetched_at,
                    next_fetch_at = excluded.next_fetch_at, failures = 0
                """,
                (
                    payload["id"],
                    event_name,
                    json.dumps(payload, ensure_ascii=False),
                    last_modified,
                    fetched_at,
                    next_fetch_at,
                ),
            )

    def get_schedule(self, schedule_id: str) -> ScheduleRow | None:
        row = self._db.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
        if row is None:
            return None
        return ScheduleRow(**{**dict(row), "payload": json.loads(row["payload"])})

    def mark_fetched(
        self,
        schedule_id: str,
        *,
        payload: dict[str, Any] | None,
        last_modified: str | None,
        fetched_at: int,
        next_fetch_at: int,
    ) -> None:
        """Record a successful fetch. `payload` is None for 304 Not Modified."""
        with self._db:
            if payload is not None:
                self._db.execute(
                    "UPDATE schedules SET payload = ? WHERE id = ?",
                    (json.dumps(payload, ensure_ascii=False), schedule_id),
                )
            self._db.execute(
                """
                UPDATE schedules SET last_modified = coalesce(?, last_modified),
                    fetched_at = ?, next_fetch_at = ?, failures = 0
                WHERE id = ?
                """,
                (last_modified, fetched_at, next_fetch_at, schedule_id),
            )

    def mark_failed(self, schedule_id: str, *, next_fetch_at: int) -> None:
        with self._db:
            self._db.execute(
                "UPDATE schedules SET failures = failures + 1, next_fetch_at = ? WHERE id = ?",
                (next_fetch_at, schedule_id),
            )

    def subscribed_schedule_ids(self) -> list[str]:
        rows = self._db.execute("SELECT DISTINCT schedule_id FROM subscriptions ORDER BY 1")
        return [r[0] for r in rows]

    # subscriptions

    def add_subscription(
        self,
        *,
        guild_id: int,
        channel_id: int,
        schedule_id: str,
        notice_minutes: int,
        key_column: str | None,
    ) -> Subscription:
        with self._db:
            cur = self._db.execute(
                """
                INSERT INTO subscriptions
                    (guild_id, channel_id, schedule_id, notice_minutes, key_column)
                VALUES (?, ?, ?, ?, ?)
                """,
                (guild_id, channel_id, schedule_id, notice_minutes, key_column),
            )
        assert cur.lastrowid is not None
        return Subscription(
            cur.lastrowid, guild_id, channel_id, schedule_id, notice_minutes, key_column, None
        )

    def get_subscription(self, guild_id: int, schedule_id: str) -> Subscription | None:
        row = self._db.execute(
            "SELECT * FROM subscriptions WHERE guild_id = ? AND schedule_id = ?",
            (guild_id, schedule_id),
        ).fetchone()
        return Subscription(**row) if row else None

    def guild_subscriptions(self, guild_id: int) -> list[Subscription]:
        rows = self._db.execute(
            "SELECT * FROM subscriptions WHERE guild_id = ? ORDER BY id", (guild_id,)
        )
        return [Subscription(**r) for r in rows]

    def schedule_subscriptions(self, schedule_id: str) -> list[Subscription]:
        rows = self._db.execute(
            "SELECT * FROM subscriptions WHERE schedule_id = ? ORDER BY id", (schedule_id,)
        )
        return [Subscription(**r) for r in rows]

    def update_subscription(self, sub: Subscription) -> None:
        with self._db:
            self._db.execute(
                """
                UPDATE subscriptions SET channel_id = ?, notice_minutes = ?, key_column = ?,
                    server_event_id = ?
                WHERE id = ? AND guild_id = ?
                """,
                (
                    sub.channel_id,
                    sub.notice_minutes,
                    sub.key_column,
                    sub.server_event_id,
                    sub.id,
                    sub.guild_id,
                ),
            )

    def remove_subscription(self, sub: Subscription) -> None:
        with self._db:
            self._db.execute(
                "DELETE FROM subscriptions WHERE id = ? AND guild_id = ?", (sub.id, sub.guild_id)
            )
            self._db.execute(
                "DELETE FROM schedules WHERE id NOT IN (SELECT schedule_id FROM subscriptions)"
            )

    # notification records

    def records(self, subscription_id: int) -> dict[str, Record]:
        rows = self._db.execute(
            "SELECT * FROM notifications WHERE subscription_id = ?", (subscription_id,)
        )
        return {
            r["item_key"]: Record(
                r["item_key"],
                r["title"],
                r["notified_t"],
                r["displayed_t"],
                r["channel_id"],
                r["message_id"],
                bool(r["removed"]),
            )
            for r in rows
        }

    def _insert_record(self, subscription_id: int, record: Record) -> None:
        self._db.execute(
            """
            INSERT OR REPLACE INTO notifications
                (subscription_id, item_key, title, notified_t, displayed_t, channel_id, message_id,
                 removed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                subscription_id,
                record.item_key,
                record.title,
                record.notified_t,
                record.displayed_t,
                record.channel_id,
                record.message_id,
                int(record.removed),
            ),
        )

    def save_record(self, subscription_id: int, record: Record) -> None:
        with self._db:
            self._insert_record(subscription_id, record)

    def rekey_records(self, subscription_id: int, mapping: dict[str, str]) -> None:
        """Rename item keys; records whose key is not in `mapping` are dropped."""
        records = self.records(subscription_id)
        with self._db:
            self._db.execute(
                "DELETE FROM notifications WHERE subscription_id = ?", (subscription_id,)
            )
            for old, record in records.items():
                if old in mapping:
                    self._insert_record(subscription_id, replace(record, item_key=mapping[old]))

    def delete_records(self, subscription_id: int) -> None:
        with self._db:
            self._db.execute(
                "DELETE FROM notifications WHERE subscription_id = ?", (subscription_id,)
            )
