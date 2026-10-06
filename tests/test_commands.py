from __future__ import annotations

from typing import Any

import aiohttp
from helpers import at, payload

from horaro_discord.bot import HoraroBot
from horaro_discord.commands import AdminGroup, HoraroGroup, order_schedules
from horaro_discord.horaro import Schedule, parse_schedule
from horaro_discord.scheduler import display_name
from horaro_discord.store import Store


async def command_payloads() -> dict[str, dict[str, Any]]:
    async with aiohttp.ClientSession() as session:
        bot = HoraroBot(Store(":memory:"), session)
        bot.tree.add_command(HoraroGroup())
        bot.tree.add_command(AdminGroup())
        return {c.name: c.to_dict(bot.tree) for c in bot.tree.get_commands()}


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
