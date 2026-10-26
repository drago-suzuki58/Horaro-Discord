from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import discord
import pytest
from helpers import at, payload, rij_payload

from horaro_discord.bot import HoraroBot
from horaro_discord.commands import (
    AdminGroup,
    HoraroGroup,
    UserError,
    find_entry,
    order_schedules,
    url_autocomplete,
)
from horaro_discord.rij import normalize_schedule
from horaro_discord.schedule import FetchResult, Schedule, ScheduleError, parse_schedule
from horaro_discord.scheduler import display_name
from horaro_discord.store import Store
from horaro_discord.timeline import Record


async def command_payloads() -> dict[str, dict[str, Any]]:
    async with aiohttp.ClientSession() as session:
        bot = HoraroBot(Store(":memory:"), session)
        bot.tree.add_command(HoraroGroup())
        bot.tree.add_command(AdminGroup())
        result = {c.name: c.to_dict(bot.tree) for c in bot.tree.get_commands()}
        bot.store.close()
        return result


def options(command: dict[str, Any], name: str) -> dict[str, dict[str, Any]]:
    sub = next(o for o in command["options"] if o["name"] == name)
    return {o["name"]: o for o in sub.get("options", [])}


async def test_command_definitions() -> None:
    commands = await command_payloads()
    assert set(commands) == {"horaro", "horaro-admin"}

    view, admin = commands["horaro"], commands["horaro-admin"]
    assert view["default_member_permissions"] is None
    assert int(admin["default_member_permissions"]) == 32  # Manage Server
    assert view["contexts"] == admin["contexts"] == [0]  # guild only

    assert {o["name"] for o in view["options"]} == {"list", "now", "upcoming"}
    assert {o["name"] for o in admin["options"]} == {"add", "remove", "edit", "refresh"}

    add = options(admin, "add")
    assert add["url"]["autocomplete"] is True
    assert add["channel"]["type"] == 7  # channel option, not a numeric ID
    assert (add["notice"]["min_value"], add["notice"]["max_value"]) == (0, 1440)

    edit = options(admin, "edit")
    assert edit["schedule"]["autocomplete"] is True
    assert edit["key_column"]["autocomplete"] is True
    assert not any(o.get("required") for name, o in edit.items() if name != "schedule")

    for name in ("now", "upcoming"):
        assert options(view, name)["schedule"]["autocomplete"] is True


def test_order_schedules_puts_open_schedules_first() -> None:
    old = payload([("A", None, 30)], start_t=at(9), schedule_id="old")
    older = payload([("A", None, 30)], start_t=at(8), schedule_id="older")
    later = payload([("A", None, 30)], start_t=at(15), schedule_id="later")
    live = payload([("A", None, 300)], start_t=at(11), schedule_id="live")
    broken: dict[str, Any] = {"id": "broken"}
    ordered = order_schedules([older, old, later, broken, live], now=at(12))
    assert [(p["id"], ended) for p, ended in ordered] == [
        ("live", False),
        ("later", False),
        ("old", True),
        ("older", True),
    ]


def test_display_name() -> None:
    def schedule(name: str) -> Schedule:
        return parse_schedule(payload([], name=name))

    assert display_name("Don't Stop Running", schedule("Don't Stop Running #22")) == (
        "Don't Stop Running #22"
    )
    assert display_name("ESA Winter 2026", schedule("winter 2026")) == "ESA Winter 2026"
    assert display_name("AGDQ 2026", schedule("Bonus Stream")) == "AGDQ 2026 / Bonus Stream"


@pytest.fixture
async def bot() -> AsyncIterator[HoraroBot]:
    store = Store(":memory:")
    async with aiohttp.ClientSession() as session:
        yield HoraroBot(store, session)
    store.close()


def interaction_for(bot: HoraroBot, guild_id: int = 1) -> Any:
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 10 * guild_id
    channel.permissions_for.return_value = discord.Permissions(
        view_channel=True, send_messages=True
    )
    return SimpleNamespace(
        client=bot,
        guild=SimpleNamespace(id=guild_id, me=object()),
        guild_id=guild_id,
        channel=channel,
        response=SimpleNamespace(defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )


async def test_add_rij_registers_source_and_preserves_existing_records(bot: HoraroBot) -> None:
    data = normalize_schedule(rij_payload([("Alpha", "ann", 30)]))
    group = AdminGroup()
    add = cast(Callable[..., Awaitable[None]], group.add.callback)
    interaction = interaction_for(bot)
    with (
        patch.object(bot.rij, "fetch_schedule", return_value=FetchResult(data, "lm")) as fetch,
        patch.object(bot.horaro, "fetch_event") as horaro,
        patch.object(bot.scheduler, "process") as process,
    ):
        await add(group, interaction, "https://rtain.jp/schedule/?event=sched1")
        fetch.assert_awaited_once_with("sched1")
        horaro.assert_not_awaited()
        process.assert_awaited_once_with("rij:sched1")
        row = bot.store.get_schedule("rij:sched1")
        assert row is not None
        assert (row.source, row.event_name, row.last_modified) == ("rij", data["name"], "lm")
        sub = bot.store.get_subscription(1, row.id)
        assert sub is not None and sub.key_column == "ゲーム" and sub.channel_id == 10
        record = Record("k:alpha#0", "Alpha", at(12), at(12), 10, 123)
        bot.store.save_record(sub.id, record)

        with pytest.raises(UserError, match="すでに登録"):
            await add(group, interaction, data["link"])
        assert bot.store.records(sub.id) == {record.item_key: record}

        await add(group, interaction_for(bot, guild_id=2), data["link"])
        assert bot.store.get_subscription(2, row.id) is not None
        assert bot.store.records(sub.id) == {record.item_key: record}
        assert find_entry(bot, 1, row.id)[0] == sub
        with pytest.raises(UserError):
            find_entry(bot, 3, row.id)


@pytest.mark.parametrize("failed_source", [None, "horaro", "rij"])
async def test_autocomplete_searches_both_sources_independently(
    bot: HoraroBot, failed_source: str | None
) -> None:
    rij = [{"name": "RTA in Japan Winter 2026", "link": "https://rtain.jp/schedule/?event=rij"}]
    horaro = [{"name": "RTA in Japan Winter 2025", "link": "https://horaro.net/rij"}]
    with (
        patch.object(
            bot.rij,
            "search_events",
            return_value=rij,
            side_effect=ScheduleError() if failed_source == "rij" else None,
        ) as rij_search,
        patch.object(
            bot.horaro,
            "search_events",
            return_value=horaro,
            side_effect=ScheduleError() if failed_source == "horaro" else None,
        ) as horaro_search,
    ):
        choices = await url_autocomplete(interaction_for(bot), "RTA in Japan")
        assert [c.value for c in choices] == [
            e["link"]
            for source, events in (("rij", rij), ("horaro", horaro))
            if source != failed_source
            for e in events
        ]
        assert all(len(c.name) <= 100 for c in choices)
        rij_search.assert_awaited_once()
        horaro_search.assert_awaited_once()


async def test_url_autocomplete_keeps_rij_url_without_search(bot: HoraroBot) -> None:
    url = "https://rtain.jp/schedule/?event=rtaijw2026"
    with patch.object(bot.rij, "search_events") as search:
        choices = await url_autocomplete(interaction_for(bot), url)
        assert [c.value for c in choices] == [url]
        search.assert_not_awaited()


async def test_rij_add_reports_fetch_errors(bot: HoraroBot) -> None:
    group = AdminGroup()
    add = cast(Callable[..., Awaitable[None]], group.add.callback)
    with (
        patch.object(bot.rij, "fetch_schedule", side_effect=ScheduleError("failed")),
        pytest.raises(UserError, match="取得できませんでした"),
    ):
        await add(group, interaction_for(bot), "https://rtain.jp/schedule/?event=rtaijw2026")
    assert bot.store.subscribed_schedule_ids() == []


async def test_add_rejects_invalid_url_without_requesting_it(bot: HoraroBot) -> None:
    group = AdminGroup()
    add = cast(Callable[..., Awaitable[None]], group.add.callback)
    with (
        patch.object(bot.rij, "fetch_schedule") as fetch,
        pytest.raises(UserError, match="URL を指定"),
    ):
        await add(group, interaction_for(bot), "https://[invalid/schedule/?event=rtaijw2026")
    fetch.assert_not_awaited()
