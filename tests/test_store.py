from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from helpers import payload

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
