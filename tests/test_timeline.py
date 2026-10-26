from __future__ import annotations

from dataclasses import replace
from typing import Any

from helpers import BASE_T, Row, at, payload

from horaro_discord.schedule import Schedule, parse_schedule
from horaro_discord.timeline import (
    IDLE_FETCH_INTERVAL,
    LIVE_FETCH_INTERVAL,
    Action,
    Edit,
    Record,
    Send,
    detect_key_column,
    item_keys,
    item_title,
    next_fetch_delay,
    now_next,
    plan,
    rekey,
    strip_markdown,
    upcoming,
)

NOTICE = 10 * 60
ROWS: list[Row] = [("Alpha", "ann", 30), ("Beta", "bob", 30), ("Gamma", "cid", 30)]


def schedule_of(rows: list[Row] = ROWS, **kw: Any) -> Schedule:
    return parse_schedule(payload(rows, **kw))


def run_plan(schedule: Schedule, records: list[Record], now: int) -> list[Action]:
    keys = item_keys(schedule, "Game")
    return plan(schedule, keys, {r.item_key: r for r in records}, now, NOTICE)


def record(key: str, t: int, *, displayed: int | None = None, removed: bool = False) -> Record:
    return Record(key, key, t, t if displayed is None else displayed, 1, 100, removed)


# keys


def test_strip_markdown() -> None:
    assert strip_markdown("[ann](https://twitch.tv/ann) & **bob**") == "ann & bob"
    assert strip_markdown("  a\n  b ") == "a b"


def test_detect_key_column() -> None:
    assert detect_key_column(("Runner", "Game", "Category")) == "Game"
    assert detect_key_column(("走者", "ゲーム", "カテゴリ")) == "ゲーム"
    assert detect_key_column(("Runner", "Category")) == "Runner"
    assert detect_key_column(()) is None


def test_item_keys_count_duplicates_and_ignore_markdown() -> None:
    schedule = schedule_of([("Alpha", "a", 10), ("[Alpha](https://x)", "b", 10), ("Beta", "c", 10)])
    assert item_keys(schedule, "Game") == ["k:alpha#0", "k:alpha#1", "k:beta#0"]


def test_item_keys_use_whole_row_when_key_is_empty() -> None:
    schedule = schedule_of([(None, "Setup block", 10), ("", "Setup block", 10)])
    assert item_keys(schedule, "Game") == ["r:|setup block#0", "r:|setup block#1"]


def test_item_keys_fall_back_when_key_column_disappears() -> None:
    schedule = schedule_of(ROWS)
    assert item_keys(schedule, "Removed column") == item_keys(schedule, "Game")


def test_item_keys_survive_runner_change() -> None:
    before = schedule_of(ROWS)
    after = schedule_of([("Alpha", "ann", 30), ("Beta", "someone else", 30), ("Gamma", "cid", 30)])
    assert item_keys(before, "Game") == item_keys(after, "Game")


def test_rekey() -> None:
    schedule = schedule_of(ROWS)
    assert rekey(schedule, "Game", "Runner") == {
        "k:alpha#0": "k:ann#0",
        "k:beta#0": "k:bob#0",
        "k:gamma#0": "k:cid#0",
    }


def test_item_title() -> None:
    schedule = schedule_of([("Alpha", "ann", 10), (None, "Break", 10), (None, None, 10)])
    assert [item_title(schedule, i, "Game") for i in schedule.items] == ["Alpha", "Break", "#3"]


# current / next


def test_now_next() -> None:
    schedule = schedule_of(ROWS, setup_min=10)  # 12:00-12:30, 12:40-13:10, 13:20-13:50
    alpha, beta, gamma = schedule.items
    before = now_next(schedule, at(11, 0))
    assert (before.current, before.next) == (None, alpha)
    assert now_next(schedule, at(12, 10)).current == alpha
    assert now_next(schedule, at(12, 10)).next == beta
    setup = now_next(schedule, at(12, 35))
    assert (setup.current, setup.next) == (None, beta)
    assert now_next(schedule, at(13, 30)).current == gamma
    assert now_next(schedule, at(13, 30)).next is None
    end = now_next(schedule, at(14, 0))
    assert (end.current, end.next) == (None, None)


def test_upcoming_includes_current_item() -> None:
    schedule = schedule_of(ROWS)
    assert [i.index for i in upcoming(schedule, at(12, 10), 5)] == [0, 1, 2]
    assert [i.index for i in upcoming(schedule, at(12, 40), 1)] == [1]


# notification planning


def test_send_when_notice_time_arrives() -> None:
    schedule = schedule_of(ROWS)
    assert run_plan(schedule, [], at(11, 49)) == []
    actions = run_plan(schedule, [], at(11, 50))
    assert actions == [Send(schedule.items[0], "k:alpha#0", None)]


def test_already_sent_items_are_not_sent_again() -> None:
    schedule = schedule_of(ROWS)
    assert run_plan(schedule, [record("k:alpha#0", BASE_T)], at(11, 55)) == []


def test_started_items_are_not_sent_after_downtime() -> None:
    schedule = schedule_of(ROWS)
    # Bot was down 11:45-12:25: Alpha started without notification, Beta is due.
    actions = run_plan(schedule, [], at(12, 25))
    assert actions == [Send(schedule.items[1], "k:beta#0", None)]


def test_registered_mid_event_sends_only_due_items() -> None:
    schedule = schedule_of(ROWS)
    actions = run_plan(schedule, [], at(12, 50))
    assert actions == [Send(schedule.items[2], "k:gamma#0", None)]


def test_delay_before_notification_moves_the_notification() -> None:
    delayed = schedule_of([("Alpha", "ann", 50), ("Beta", "bob", 30), ("Gamma", "cid", 30)])
    sent = [record("k:alpha#0", BASE_T)]
    # Beta was 12:30 and is now 12:50: nothing at the old notice time 12:20.
    assert run_plan(delayed, sent, at(12, 20)) == []
    assert run_plan(delayed, sent, at(12, 40)) == [Send(delayed.items[1], "k:beta#0", None)]


def test_delay_after_notification_edits_and_renotifies() -> None:
    sent = [record("k:beta#0", at(12, 30))]
    delayed = schedule_of([("Alpha", "ann", 50), ("Beta", "bob", 30), ("Gamma", "cid", 30)])
    beta = delayed.items[1]

    actions = run_plan(delayed, sent, at(12, 25))
    assert actions == [Edit(sent[0], beta)]

    edited = replace(sent[0], displayed_t=beta.scheduled_t)
    assert run_plan(delayed, [edited], at(12, 30)) == []
    assert run_plan(delayed, [edited], at(12, 40)) == [Send(beta, "k:beta#0", at(12, 30))]


def test_delay_noticed_after_old_start_is_still_handled() -> None:
    # Beta was announced for 12:30. At 12:31 it has not started and is moved to 12:50.
    sent = [record("k:beta#0", at(12, 30))]
    delayed = schedule_of([("Alpha", "ann", 50), ("Beta", "bob", 30), ("Gamma", "cid", 30)])
    actions = run_plan(delayed, sent, at(12, 31))
    assert actions == [Edit(sent[0], delayed.items[1])]


def test_small_shift_only_edits() -> None:
    sent = [record("k:beta#0", at(12, 30))]
    shifted = schedule_of([("Alpha", "ann", 33), ("Beta", "bob", 30), ("Gamma", "cid", 30)])
    beta = shifted.items[1]
    assert run_plan(shifted, sent, at(12, 25)) == [Edit(sent[0], beta)]
    edited = replace(sent[0], displayed_t=beta.scheduled_t)
    assert run_plan(shifted, [edited], at(12, 28)) == []


def test_moved_earlier_sends_immediately() -> None:
    sent = [record("k:gamma#0", at(13, 0))]
    earlier = schedule_of([("Alpha", "ann", 30), ("Beta", "bob", 10), ("Gamma", "cid", 30)])
    gamma = earlier.items[2]  # now 12:40
    actions = run_plan(earlier, sent, at(12, 35))
    assert actions == [Edit(sent[0], gamma), Send(gamma, "k:gamma#0", at(13, 0))]


def test_removed_item_is_marked() -> None:
    sent = [record("k:gamma#0", at(13, 0))]
    removed = schedule_of([("Alpha", "ann", 30), ("Beta", "bob", 30)])
    assert run_plan(removed, sent, at(12, 55)) == [Edit(sent[0], None)]
    marked = replace(sent[0], removed=True)
    assert run_plan(removed, [marked], at(12, 56)) == []


def test_removed_item_that_returns_is_restored() -> None:
    marked = record("k:gamma#0", at(13, 0), removed=True)
    schedule = schedule_of(ROWS)
    assert run_plan(schedule, [marked], at(12, 55)) == [Edit(marked, schedule.items[2])]


def test_inserted_item_shifts_everything_after_it() -> None:
    sent = [record("k:beta#0", at(12, 30))]
    inserted = schedule_of(
        [("Alpha", "ann", 30), ("Bonus", "zed", 20), ("Beta", "bob", 30), ("Gamma", "cid", 30)]
    )
    bonus, beta = inserted.items[1], inserted.items[2]
    actions = run_plan(inserted, sent, at(12, 22))
    assert actions == [Send(bonus, "k:bonus#0", None), Edit(sent[0], beta)]


def test_finished_items_are_left_alone() -> None:
    sent = [record("k:alpha#0", at(12, 0))]
    changed = schedule_of([("Alpha", "ann", 30)], start_t=at(12, 5))
    assert run_plan(changed, sent, at(13, 0)) == []


def test_edit_and_send_never_target_items_without_change() -> None:
    schedule = schedule_of(ROWS)
    keys = item_keys(schedule, "Game")
    records = [record(k, i.scheduled_t) for k, i in zip(keys, schedule.items, strict=True)]
    for minute in range(0, 120, 5):
        assert run_plan(schedule, records, at(11, 30) + minute * 60) == []


# fetch timing


def test_next_fetch_delay() -> None:
    schedule = schedule_of(ROWS)  # 12:00-13:30
    # The live window starts at 11:20 (30 minutes before the first notification).
    assert next_fetch_delay(schedule, at(10, 0), NOTICE, 0) == IDLE_FETCH_INTERVAL
    assert next_fetch_delay(schedule, at(11, 0), NOTICE, 0) == 20 * 60
    assert next_fetch_delay(schedule, at(11, 19, 30), NOTICE, 0) == LIVE_FETCH_INTERVAL
    assert next_fetch_delay(schedule, at(11, 20), NOTICE, 0) == LIVE_FETCH_INTERVAL
    assert next_fetch_delay(schedule, at(13, 59), NOTICE, 0) == LIVE_FETCH_INTERVAL
    assert next_fetch_delay(schedule, at(14, 1), NOTICE, 0) == IDLE_FETCH_INTERVAL
    assert next_fetch_delay(schedule, at(12, 0), NOTICE, 1) == 2 * LIVE_FETCH_INTERVAL
    assert next_fetch_delay(schedule, at(12, 0), NOTICE, 50) == IDLE_FETCH_INTERVAL
