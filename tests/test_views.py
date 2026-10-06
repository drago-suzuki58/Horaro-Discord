from __future__ import annotations

from discord import ui
from helpers import Row, at, payload

from horaro_discord.horaro import parse_schedule
from horaro_discord.scheduler import Kind, Notification
from horaro_discord.views import (
    ScheduleInfo,
    SubscriptionInfo,
    length,
    notification_view,
    now_view,
    subscriptions_view,
    upcoming_view,
)

# Discord limits for Components V2 messages.
MAX_COMPONENTS = 40
MAX_TEXT = 4000


def text_of(view: ui.LayoutView) -> str:
    assert view.total_children_count <= MAX_COMPONENTS
    assert view.content_length() <= MAX_TEXT
    return "\n".join(c.content for c in view.walk_children() if isinstance(c, ui.TextDisplay))


def notification(kind: Kind, previous_t: int | None = None, **kw: object) -> Notification:
    fields: dict[str, object] = {
        "kind": kind,
        "schedule_name": "Test Event / Day 1",
        "link": "https://horaro.net/testev/day1",
        "title": "Alpha",
        "scheduled_t": at(12, 50),
        "previous_t": previous_t,
        "length_t": 3900,
        "details": (("Runner", "[ann](https://twitch.tv/ann)"),),
    }
    fields.update(kw)
    return Notification(**fields)  # type: ignore[arg-type]


def test_length() -> None:
    assert length(3900) == "1:05:00"
    assert length(59) == "0:00:59"


async def test_notice() -> None:
    text = text_of(notification_view(notification(Kind.NOTICE)))
    assert "### Alpha" in text
    assert f"<t:{at(12, 50)}:t>" in text and f"<t:{at(12, 50)}:R>" in text
    assert "**Runner**: [ann](https://twitch.tv/ann)" in text
    assert "**予定時間**: 1:05:00" in text
    assert "予定変更" not in text


async def test_changed_and_renotice_show_previous_time() -> None:
    changed = text_of(notification_view(notification(Kind.CHANGED, at(12, 30))))
    assert f"~~<t:{at(12, 30)}:t>~~ → <t:{at(12, 50)}:t>" in changed
    renotice = text_of(notification_view(notification(Kind.RENOTICE, at(12, 30))))
    assert "予定変更" in renotice and f"~~<t:{at(12, 30)}:t>~~" in renotice


async def test_removed() -> None:
    text = text_of(notification_view(notification(Kind.REMOVED, length_t=None, details=())))
    assert "~~Alpha~~" in text and "削除" in text


async def test_long_values_fit_discord_limits() -> None:
    details = tuple((f"Column {i}", "x" * 1000) for i in range(40))
    text_of(notification_view(notification(Kind.NOTICE, title="t" * 1000, details=details)))


def info() -> ScheduleInfo:
    rows: list[Row] = [("Alpha", "ann", 30), ("Beta", "bob", 30)]
    return ScheduleInfo("Test Event", parse_schedule(payload(rows, setup_min=10)), "Game")


async def test_now_view_states() -> None:
    assert "開始前" in text_of(now_view([info()], at(11, 0)))
    during = text_of(now_view([info()], at(12, 10)))
    assert "**現在**: Alpha" in during and "**次**: Beta" in during
    assert "**現在**: 準備中" in text_of(now_view([info()], at(12, 35)))
    assert "終了しました" in text_of(now_view([info()], at(14, 0)))


async def test_now_view_many_schedules() -> None:
    text_of(now_view([info()] * 10, at(12, 10)))


async def test_upcoming_view() -> None:
    schedule = info().schedule
    text = text_of(upcoming_view(info(), schedule.items, at(12, 10)))
    assert "**現在** **Alpha**" in text
    assert "-# bob" in text


async def test_subscriptions_view() -> None:
    sub = SubscriptionInfo(info(), channel_id=123, notice_minutes=10, server_event=True)
    text = text_of(subscriptions_view([sub] * 10, header="### 登録しました"))
    assert "<#123>" in text and "連携中" in text
