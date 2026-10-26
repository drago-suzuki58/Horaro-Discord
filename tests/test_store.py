from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path

from helpers import payload, rij_payload

from horaro_discord.rij import normalize_schedule
from horaro_discord.store import Store
from horaro_discord.timeline import Record


def make_store(path: str | Path = ":memory:") -> Store:
    store = Store(path)
    store.save_schedule(
        payload([("Alpha", "ann", 30)]),
        event_name="Test Event",
        last_modified="lm",
        fetched_at=100,
        next_fetch_at=160,
    )
    return store


def subscribe(store: Store, guild_id: int) -> int:
    sub = store.add_subscription(
        guild_id=guild_id,
        channel_id=guild_id * 10,
        schedule_id="sched1",
        notice_minutes=10,
        key_column="Game",
    )
    return sub.id


def test_schedule_fetch_state() -> None:
    store = make_store()
    row = store.get_schedule("sched1")
    assert row is not None
    assert (row.event_name, row.last_modified, row.failures) == ("Test Event", "lm", 0)
    assert row.schedule.items[0].values == ("Alpha", "ann")

    store.mark_failed("sched1", next_fetch_at=300)
    store.mark_failed("sched1", next_fetch_at=400)
    row = store.get_schedule("sched1")
    assert row is not None
    assert (row.failures, row.next_fetch_at) == (2, 400)

    # 304: keeps the payload and Last-Modified.
    store.mark_fetched(
        "sched1", payload=None, last_modified=None, fetched_at=500, next_fetch_at=560
    )
    row = store.get_schedule("sched1")
    assert row is not None
    assert (row.failures, row.last_modified, row.fetched_at) == (0, "lm", 500)
    assert row.schedule.items[0].values == ("Alpha", "ann")

    new = payload([("Beta", "bob", 30)])
    store.mark_fetched(
        "sched1", payload=new, last_modified="lm2", fetched_at=600, next_fetch_at=660
    )
    row = store.get_schedule("sched1")
    assert row is not None
    assert (row.payload, row.last_modified) == (new, "lm2")


def test_subscriptions_are_scoped_by_guild() -> None:
    store = make_store()
    subscribe(store, 1)
    subscribe(store, 2)
    assert store.subscribed_schedule_ids() == ["sched1"]

    sub1 = store.get_subscription(1, "sched1")
    sub2 = store.get_subscription(2, "sched1")
    assert sub1 is not None and sub2 is not None

    # An update that names another guild's row changes nothing.
    store.update_subscription(replace(sub2, guild_id=1, notice_minutes=99))
    assert store.get_subscription(2, "sched1") == sub2

    store.update_subscription(replace(sub1, notice_minutes=5, server_event_id=7))
    assert store.get_subscription(1, "sched1") == replace(sub1, notice_minutes=5, server_event_id=7)
    assert store.get_subscription(2, "sched1") == sub2

    store.remove_subscription(sub1)
    assert store.get_subscription(1, "sched1") is None
    assert store.guild_subscriptions(2) == [sub2]
    assert store.get_schedule("sched1") is not None

    store.remove_subscription(sub2)
    assert store.get_schedule("sched1") is None
    assert store.subscribed_schedule_ids() == []


def test_records() -> None:
    store = make_store()
    sub_id = subscribe(store, 1)
    other_id = subscribe(store, 2)
    a = Record("k:alpha#0", "Alpha", 1000, 1000, 10, 555)
    b = Record("k:beta#0", "Beta", 2000, 2000, 10, None)
    store.save_record(sub_id, a)
    store.save_record(sub_id, b)
    store.save_record(other_id, a)
    store.save_record(sub_id, replace(a, displayed_t=1500, removed=True))
    assert store.records(sub_id) == {
        a.item_key: replace(a, displayed_t=1500, removed=True),
        b.item_key: b,
    }

    store.rekey_records(sub_id, {"k:alpha#0": "k:ann#0"})
    assert store.records(sub_id) == {
        "k:ann#0": replace(a, item_key="k:ann#0", displayed_t=1500, removed=True)
    }

    store.delete_records(sub_id)
    assert store.records(sub_id) == {}
    assert store.records(other_id) == {a.item_key: a}


def test_removing_subscription_deletes_its_records() -> None:
    store = make_store()
    sub_id = subscribe(store, 1)
    store.save_record(sub_id, Record("k", "t", 1, 1, 10, 1))
    sub = store.get_subscription(1, "sched1")
    assert sub is not None
    store.remove_subscription(sub)
    assert store.records(sub_id) == {}


def test_reopen_file(tmp_path: Path) -> None:
    path = tmp_path / "data" / "test.db"
    store = make_store(path)
    subscribe(store, 1)
    store.close()
    reopened = Store(path)
    assert reopened.get_subscription(1, "sched1") is not None
    reopened.close()


def test_migration_preserves_horaro_state(tmp_path: Path) -> None:
    path = tmp_path / "v1.db"
    data = payload([("Alpha", "ann", 30)])
    with sqlite3.connect(path) as db:
        db.executescript((Path(__file__).parent / "fixtures" / "store_v1.sql").read_text())
        db.execute(
            "INSERT INTO schedules VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("sched1", "Test Event", json.dumps(data), "lm", 100, 160, 2),
        )
        db.execute(
            "INSERT INTO subscriptions VALUES (?, ?, ?, ?, ?, ?, ?)",
            (42, 1, 10, "sched1", 5, "Game", 99),
        )
        db.execute(
            "INSERT INTO notifications VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (42, "k:alpha#0", "Alpha", 1000, 1200, 10, 555, 1),
        )
    db.close()

    for _ in range(2):  # Reopening must not try to migrate again.
        store = Store(path)
        row = store.get_schedule("sched1")
        assert row is not None
        assert (row.source, row.payload, row.last_modified) == ("horaro", data, "lm")
        assert (row.fetched_at, row.next_fetch_at, row.failures) == (100, 160, 2)
        sub = store.get_subscription(1, "sched1")
        assert sub is not None
        assert (sub.id, sub.notice_minutes, sub.key_column, sub.server_event_id) == (
            42,
            5,
            "Game",
            99,
        )
        assert store.records(42) == {
            "k:alpha#0": Record("k:alpha#0", "Alpha", 1000, 1200, 10, 555, True)
        }
        store.close()
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    db.close()


def test_sources_with_same_remote_id_are_independent(tmp_path: Path) -> None:
    path = tmp_path / "sources.db"
    store = make_store(path)
    subscribe(store, 1)
    rij_data = normalize_schedule(rij_payload([("Beta", "bob", 30)]))
    store.save_schedule(
        rij_data,
        source="rij",
        event_name=rij_data["name"],
        last_modified="rij-lm",
        fetched_at=200,
        next_fetch_at=260,
    )
    sub = store.add_subscription(
        guild_id=1, channel_id=10, schedule_id="rij:sched1", notice_minutes=10, key_column="ゲーム"
    )
    store.save_record(sub.id, Record("k:beta#0", "Beta", 1000, 1000, 10, 123))
    store.close()

    store = Store(path)
    row = store.get_schedule("rij:sched1")
    assert row is not None and row.source == "rij" and row.payload == rij_data
    assert store.subscribed_schedule_ids() == ["rij:sched1", "sched1"]
    assert store.get_subscription(1, "rij:sched1") == sub
    assert store.records(sub.id)["k:beta#0"].message_id == 123
    store.remove_subscription(sub)
    assert store.get_schedule("rij:sched1") is None
    assert store.get_subscription(1, "sched1") is not None
    store.close()
