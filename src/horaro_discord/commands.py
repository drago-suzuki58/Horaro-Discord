from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any, cast
from urllib.parse import urlsplit

import discord
from discord import app_commands, ui

from .bot import HoraroBot
from .horaro import HoraroClient, event_api_url, parse_url
from .rij import RijClient
from .rij import parse_url as parse_rij_url
from .schedule import ScheduleError, ScheduleNotFound, parse_schedule
from .scheduler import FetchOutcome, display_name
from .store import ScheduleRow, Subscription
from .timeline import (
    detect_key_column,
    effective_key_column,
    next_fetch_delay,
    rekey,
    server_event_times,
    upcoming,
)
from .views import (
    ScheduleInfo,
    SubscriptionInfo,
    clip,
    now_view,
    subscriptions_view,
    text_view,
    upcoming_view,
)

log = logging.getLogger(__name__)

MAX_SHOWN = 10
AUTOCOMPLETE_TIMEOUT = 2.0

Sendable = discord.TextChannel | discord.VoiceChannel | discord.Thread
GUILD_ONLY = app_commands.AppCommandContext(guild=True, dm_channel=False, private_channel=False)


class UserError(Exception):
    """An error whose message is shown to the user as is."""


def bot_of(interaction: discord.Interaction) -> HoraroBot:
    return cast(HoraroBot, interaction.client)


def guild_of(interaction: discord.Interaction) -> discord.Guild:
    if interaction.guild is None:
        raise UserError("サーバー内で実行してください。")
    return interaction.guild


def schedule_info(row: ScheduleRow, sub: Subscription) -> ScheduleInfo:
    schedule = row.schedule
    return ScheduleInfo(
        display_name(row.event_name, schedule),
        schedule,
        effective_key_column(schedule, sub.key_column),
    )


def subscription_info(row: ScheduleRow, sub: Subscription) -> SubscriptionInfo:
    return SubscriptionInfo(
        schedule_info(row, sub), sub.channel_id, sub.notice_minutes, sub.server_event_id is not None
    )


def guild_entries(bot: HoraroBot, guild_id: int) -> list[tuple[Subscription, ScheduleRow]]:
    entries = []
    for sub in bot.store.guild_subscriptions(guild_id):
        row = bot.store.get_schedule(sub.schedule_id)
        if row is not None:
            entries.append((sub, row))
    return entries


def find_entry(bot: HoraroBot, guild_id: int, value: str) -> tuple[Subscription, ScheduleRow]:
    """Find a subscription by schedule ID (autocomplete value) or by part of its name."""
    entries = guild_entries(bot, guild_id)
    for sub, row in entries:
        if sub.schedule_id == value:
            return sub, row
    matches = [
        (sub, row)
        for sub, row in entries
        if value.casefold() in display_name(row.event_name, row.schedule).casefold()
    ]
    if len(matches) != 1:
        raise UserError("スケジュールが見つかりません。候補から選んでください。")
    return matches[0]


async def schedule_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    if interaction.guild_id is None:
        return []
    choices = []
    for sub, row in guild_entries(bot_of(interaction), interaction.guild_id):
        name = display_name(row.event_name, row.schedule)
        if current.casefold() in name.casefold():
            choices.append(app_commands.Choice(name=clip(name, 100), value=sub.schedule_id))
    return choices[:25]


async def url_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    current = current.strip()
    if not current:
        return []
    if parse_url(current) or "/" in current:
        return [app_commands.Choice(name=clip(current, 100), value=current[:100])]

    async def search(client: HoraroClient | RijClient) -> list[dict[str, Any]]:
        try:
            return await client.search_events(current, AUTOCOMPLETE_TIMEOUT)
        except ScheduleError:
            return []

    bot = bot_of(interaction)
    rij_events, horaro_events = await asyncio.gather(search(bot.rij), search(bot.horaro))
    choices: list[app_commands.Choice[str]] = []
    for source, events in (("RiJ公式", rij_events), ("Horaro", horaro_events)):
        choices.extend(
            app_commands.Choice(name=clip(f"{e['name']}（{source}）", 100), value=str(e["link"]))
            for e in events
        )
    return choices[:25]


async def key_column_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    schedule = getattr(interaction.namespace, "schedule", None)
    if interaction.guild_id is None or not schedule:
        return []
    try:
        _, row = find_entry(bot_of(interaction), interaction.guild_id, schedule)
    except UserError:
        return []
    return [
        app_commands.Choice(name=clip(c, 100), value=c[:100])
        for c in row.schedule.columns
        if current.casefold() in c.casefold()
    ][:25]


async def report_error(interaction: discord.Interaction, error: Exception) -> None:
    if isinstance(error, app_commands.CommandInvokeError):
        error = error.original
    if isinstance(error, UserError):
        message = str(error)
    else:
        log.error("Interaction failed", exc_info=error)
        message = "エラーが発生しました。"
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


def check_channel(guild: discord.Guild, channel: Any) -> Sendable:
    if not isinstance(channel, Sendable):
        raise UserError("このチャンネルには通知できません。テキストチャンネルを指定してください。")
    perms = channel.permissions_for(guild.me)
    can_send = (
        perms.send_messages_in_threads
        if isinstance(channel, discord.Thread)
        else (perms.send_messages)
    )
    if not (perms.view_channel and can_send):
        raise UserError(f"Bot に {channel.mention} へメッセージを送る権限がありません。")
    return channel


async def enable_server_event(
    bot: HoraroBot, guild: discord.Guild, sub: Subscription, row: ScheduleRow
) -> tuple[Subscription, str]:
    perms = guild.me.guild_permissions
    if not (perms.create_events or perms.manage_events):
        return sub, "Bot に「イベントの作成」権限がないため、サーバーイベントは作成しませんでした。"
    start_t, _ = server_event_times(row.schedule)
    if start_t <= time.time() + 60:
        return sub, "スケジュールがすでに開始しているため、サーバーイベントは作成しませんでした。"
    try:
        event = await bot.adapter.create_server_event(
            guild, display_name(row.event_name, row.schedule), row.schedule
        )
    except discord.HTTPException as e:
        return sub, f"サーバーイベントを作成できませんでした: {e.text}"
    sub = replace(sub, server_event_id=event.id)
    bot.store.update_subscription(sub)
    return sub, "サーバーイベントを作成しました。"


async def disable_server_event(bot: HoraroBot, sub: Subscription) -> Subscription:
    if sub.server_event_id is None:
        return sub
    try:
        await bot.adapter.delete_server_event(sub.guild_id, sub.server_event_id)
    except discord.HTTPException as e:
        log.warning("Failed to delete server event %s: %s", sub.server_event_id, e)
    sub = replace(sub, server_event_id=None)
    bot.store.update_subscription(sub)
    return sub


async def event_name_of(bot: HoraroBot, payload: dict[str, Any]) -> str:
    url = event_api_url(payload)
    if url:
        try:
            return str((await bot.horaro.fetch_event(url))["name"])
        except (ScheduleError, KeyError) as e:
            log.warning("Failed to fetch event of schedule %s: %s", payload.get("id"), e)
    return urlsplit(str(payload.get("link", ""))).path.strip("/").split("/")[0]


async def register(
    bot: HoraroBot,
    guild: discord.Guild,
    channel: Sendable,
    payload: dict[str, Any],
    last_modified: str | None,
    notice: int,
    server_event: bool,
    *,
    source: str = "horaro",
) -> ui.LayoutView:
    try:
        schedule = parse_schedule(payload)
    except (KeyError, ValueError, TypeError) as e:
        raise UserError("スケジュールの形式を読み取れませんでした。") from e
    if bot.store.get_subscription(guild.id, schedule.id):
        raise UserError(
            "このスケジュールはすでに登録されています。変更は `/horaro-admin edit` で行えます。"
        )
    now = int(time.time())
    bot.store.save_schedule(
        payload,
        event_name=str(payload["name"]) if source == "rij" else await event_name_of(bot, payload),
        last_modified=last_modified,
        fetched_at=now,
        next_fetch_at=now + next_fetch_delay(schedule, now, notice * 60, 0),
        source=source,
    )
    sub = bot.store.add_subscription(
        guild_id=guild.id,
        channel_id=channel.id,
        schedule_id=schedule.id,
        notice_minutes=notice,
        key_column=detect_key_column(schedule.columns),
    )
    row = bot.store.get_schedule(schedule.id)
    assert row is not None
    header = "### 登録しました"
    if server_event:
        sub, note = await enable_server_event(bot, guild, sub, row)
        header += "\n" + note
    log.info("Guild %s subscribed to schedule %s", guild.id, schedule.id)
    return subscriptions_view([subscription_info(row, sub)], header=header)


class CallbackButton(ui.Button[ui.LayoutView]):
    def __init__(
        self,
        label: str,
        style: discord.ButtonStyle,
        callback: Callable[[discord.Interaction], Awaitable[None]],
    ) -> None:
        super().__init__(label=label, style=style)
        self._callback = callback

    async def callback(self, interaction: discord.Interaction) -> None:
        await self._callback(interaction)


class BaseLayout(ui.LayoutView):
    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: ui.Item[Any]
    ) -> None:
        await report_error(interaction, error)


def order_schedules(payloads: list[dict[str, Any]], now: int) -> list[tuple[dict[str, Any], bool]]:
    """Schedules that have not ended (soonest first), then ended ones (latest first).

    Returns pairs of (payload, ended). Payloads that cannot be parsed are left out.
    """
    entries = []
    for p in payloads:
        try:
            schedule = parse_schedule(p)
        except (KeyError, ValueError, TypeError):
            continue
        ended = schedule.end_t <= now
        entries.append((ended, -schedule.start_t if ended else schedule.start_t, p))
    entries.sort(key=lambda e: (e[0], e[1]))
    return [(p, ended) for ended, _, p in entries]


class ScheduleSelect(ui.Select[ui.LayoutView]):
    def __init__(
        self,
        ordered: list[tuple[dict[str, Any], bool]],
        on_select: Callable[[discord.Interaction, dict[str, Any]], Awaitable[None]],
    ) -> None:
        options = [
            discord.SelectOption(
                label=clip(str(p["name"]), 100),
                value=str(i),
                description=f"{str(p['start'])[:16].replace('T', ' ')} 開始"
                + ("（終了済み）" if ended else ""),
            )
            for i, (p, ended) in enumerate(ordered)
        ]
        super().__init__(placeholder="スケジュールを選択", options=options)
        self._schedules = [p for p, _ in ordered]
        self._on_select = on_select

    async def callback(self, interaction: discord.Interaction) -> None:
        await self._on_select(interaction, self._schedules[int(self.values[0])])


class AddScheduleSelectView(BaseLayout):
    def __init__(
        self,
        schedules: list[dict[str, Any]],
        channel: Sendable,
        notice: int,
        server_event: bool,
    ) -> None:
        super().__init__(timeout=300)
        self.channel = channel
        self.notice = notice
        self.server_event = server_event
        ordered = order_schedules(schedules, int(time.time()))
        text = (
            "このイベントには複数のスケジュールがあります。登録するスケジュールを選んでください。"
        )
        if len(ordered) > 25:
            text += (
                f"\n（{len(ordered)} 件のうち、開催前・開催中のものを優先して"
                " 25 件を表示しています。他はスケジュールの URL を指定してください）"
            )
        self.add_item(ui.TextDisplay(text))
        self.add_item(ui.ActionRow(ScheduleSelect(ordered[:25], self._selected)))

    async def _selected(self, interaction: discord.Interaction, payload: dict[str, Any]) -> None:
        await interaction.response.defer()
        bot = bot_of(interaction)
        try:
            view = await register(
                bot,
                guild_of(interaction),
                self.channel,
                payload,
                None,
                self.notice,
                self.server_event,
            )
        except UserError as e:
            await interaction.edit_original_response(view=text_view(str(e)))
            return
        self.stop()
        await interaction.edit_original_response(view=view)
        await bot.scheduler.process(str(payload["id"]))


class ConfirmRemoveView(BaseLayout):
    def __init__(self, sub: Subscription, name: str) -> None:
        super().__init__(timeout=120)
        self.sub = sub
        text = f"**{name}** の登録を解除しますか？\n送信済みの通知メッセージは残ります。"
        if sub.server_event_id is not None:
            text += "\n開始前のサーバーイベントは削除されます。"
        self.add_item(ui.TextDisplay(text))
        self.add_item(
            ui.ActionRow(
                CallbackButton("解除する", discord.ButtonStyle.danger, self._confirm),
                CallbackButton("キャンセル", discord.ButtonStyle.secondary, self._cancel),
            )
        )

    async def _confirm(self, interaction: discord.Interaction) -> None:
        bot = bot_of(interaction)
        async with bot.scheduler.lock(self.sub.schedule_id):
            sub = bot.store.get_subscription(self.sub.guild_id, self.sub.schedule_id)
            if sub is not None:
                await disable_server_event(bot, sub)
                bot.store.remove_subscription(sub)
                log.info("Guild %s unsubscribed from schedule %s", sub.guild_id, sub.schedule_id)
        self.stop()
        await interaction.response.edit_message(view=text_view("登録を解除しました。"))

    async def _cancel(self, interaction: discord.Interaction) -> None:
        self.stop()
        await interaction.response.edit_message(view=text_view("キャンセルしました。"))


class HoraroGroup(app_commands.Group):
    def __init__(self) -> None:
        super().__init__(
            name="horaro",
            description="Horaro・RTA in Japan のスケジュールを表示します",
            allowed_contexts=GUILD_ONLY,
        )

    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await report_error(interaction, error)

    @app_commands.command(
        name="list", description="このサーバーに登録されたスケジュールを表示します"
    )
    async def list_(self, interaction: discord.Interaction) -> None:
        entries = guild_entries(bot_of(interaction), guild_of(interaction).id)
        if not entries:
            raise UserError(
                "登録されたスケジュールはありません。`/horaro-admin add` で登録できます。"
            )
        infos = [subscription_info(row, sub) for sub, row in entries[:MAX_SHOWN]]
        await interaction.response.send_message(view=subscriptions_view(infos))

    @app_commands.command(name="now", description="現在と次のプログラムを表示します")
    @app_commands.describe(schedule="スケジュール（省略すると登録済みのすべて）")
    @app_commands.autocomplete(schedule=schedule_autocomplete)
    async def now(self, interaction: discord.Interaction, schedule: str | None = None) -> None:
        bot = bot_of(interaction)
        guild_id = guild_of(interaction).id
        if schedule:
            entries = [find_entry(bot, guild_id, schedule)]
        else:
            entries = guild_entries(bot, guild_id)
        if not entries:
            raise UserError(
                "登録されたスケジュールはありません。`/horaro-admin add` で登録できます。"
            )
        infos = [schedule_info(row, sub) for sub, row in entries[:MAX_SHOWN]]
        await interaction.response.send_message(view=now_view(infos, int(time.time())))

    @app_commands.command(name="upcoming", description="今後のプログラムを表示します")
    @app_commands.describe(schedule="スケジュール", count="表示する件数")
    @app_commands.autocomplete(schedule=schedule_autocomplete)
    async def upcoming(
        self,
        interaction: discord.Interaction,
        schedule: str,
        count: app_commands.Range[int, 1, MAX_SHOWN] = 5,
    ) -> None:
        sub, row = find_entry(bot_of(interaction), guild_of(interaction).id, schedule)
        now = int(time.time())
        items = upcoming(row.schedule, now, count)
        view = upcoming_view(schedule_info(row, sub), items, now)
        await interaction.response.send_message(view=view)


class AdminGroup(app_commands.Group):
    def __init__(self) -> None:
        super().__init__(
            name="horaro-admin",
            description="Horaro・RTA in Japan のスケジュール通知を管理します",
            allowed_contexts=GUILD_ONLY,
            default_permissions=discord.Permissions(manage_guild=True),
        )

    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await report_error(interaction, error)

    @app_commands.command(name="add", description="スケジュールを登録して通知を始めます")
    @app_commands.describe(
        url="スケジュールまたはイベントの URL（イベント名を入力すると検索します）",
        channel="通知するチャンネル（省略すると実行したチャンネル）",
        notice="開始の何分前に通知するか",
        server_event="Discord のサーバーイベントを作成し、スケジュールに合わせて更新するか",
    )
    @app_commands.autocomplete(url=url_autocomplete)
    async def add(
        self,
        interaction: discord.Interaction,
        url: str,
        channel: discord.TextChannel | None = None,
        notice: app_commands.Range[int, 0, 1440] = 10,
        server_event: bool = False,
    ) -> None:
        guild = guild_of(interaction)
        target = check_channel(guild, channel or interaction.channel)
        rij_event = parse_rij_url(url)
        ref = parse_url(url)
        if ref is None and rij_event is None:
            raise UserError(
                "Horaro または RTA in Japan のスケジュール URL を指定してください。\n"
                "例: https://horaro.net/event/schedule\n"
                "例: https://rtain.jp/schedule/?event=rtaijw2026"
            )
        await interaction.response.defer(ephemeral=True, thinking=True)
        bot = bot_of(interaction)
        source = "rij" if rij_event is not None else "horaro"
        try:
            if rij_event is not None:
                result = await bot.rij.fetch_schedule(rij_event)
                assert result.data is not None
                payload, last_modified = result.data, result.last_modified
            elif ref is not None and ref.schedule is None:
                schedules = await bot.horaro.list_event_schedules(ref.event)
                if not schedules:
                    raise UserError("このイベントには公開されているスケジュールがありません。")
                if len(schedules) > 1:
                    select = AddScheduleSelectView(schedules, target, notice, server_event)
                    await interaction.followup.send(view=select, ephemeral=True)
                    return
                payload, last_modified = schedules[0], None
            else:
                assert ref is not None and ref.schedule is not None
                result = await bot.horaro.fetch_schedule_by_slug(ref.event, ref.schedule)
                assert result.data is not None
                payload, last_modified = result.data, result.last_modified
        except ScheduleNotFound as e:
            raise UserError(
                "見つかりませんでした。公開されているスケジュールの URL か確認してください。"
            ) from e
        except ScheduleError as e:
            log.warning("Failed to fetch %s: %s", url, e)
            raise UserError(
                "スケジュールを取得できませんでした。時間をおいて再度お試しください。"
            ) from e

        view = await register(
            bot, guild, target, payload, last_modified, notice, server_event, source=source
        )
        await interaction.followup.send(view=view, ephemeral=True)
        await bot.scheduler.process(str(payload["id"]))

    @app_commands.command(name="remove", description="スケジュールの登録を解除します")
    @app_commands.describe(schedule="スケジュール")
    @app_commands.autocomplete(schedule=schedule_autocomplete)
    async def remove(self, interaction: discord.Interaction, schedule: str) -> None:
        sub, row = find_entry(bot_of(interaction), guild_of(interaction).id, schedule)
        view = ConfirmRemoveView(sub, display_name(row.event_name, row.schedule))
        await interaction.response.send_message(view=view, ephemeral=True)

    @app_commands.command(name="edit", description="登録内容を変更します")
    @app_commands.describe(
        schedule="スケジュール",
        channel="通知するチャンネル",
        notice="開始の何分前に通知するか",
        key_column="通知の見出しにする列。プログラムの識別にも使います",
        server_event="Discord のサーバーイベントを作成し、スケジュールに合わせて更新するか",
    )
    @app_commands.autocomplete(schedule=schedule_autocomplete, key_column=key_column_autocomplete)
    async def edit(
        self,
        interaction: discord.Interaction,
        schedule: str,
        channel: discord.TextChannel | None = None,
        notice: app_commands.Range[int, 0, 1440] | None = None,
        key_column: str | None = None,
        server_event: bool | None = None,
    ) -> None:
        bot = bot_of(interaction)
        guild = guild_of(interaction)
        sub, row = find_entry(bot, guild.id, schedule)
        if channel is None and notice is None and key_column is None and server_event is None:
            raise UserError("変更する項目を指定してください。")
        if key_column is not None and key_column not in row.schedule.columns:
            raise UserError(f"列「{key_column}」はありません。候補から選んでください。")
        if channel is not None:
            check_channel(guild, channel)
        await interaction.response.defer(ephemeral=True, thinking=True)

        notes = []
        async with bot.scheduler.lock(sub.schedule_id):
            if channel is not None:
                sub = replace(sub, channel_id=channel.id)
            if notice is not None:
                sub = replace(sub, notice_minutes=notice)
            if key_column is not None:
                mapping = rekey(row.schedule, sub.key_column, key_column)
                bot.store.rekey_records(sub.id, mapping)
                sub = replace(sub, key_column=key_column)
            bot.store.update_subscription(sub)
            if server_event and sub.server_event_id is None:
                sub, note = await enable_server_event(bot, guild, sub, row)
                notes.append(note)
            elif server_event is False and sub.server_event_id is not None:
                sub = await disable_server_event(bot, sub)
                notes.append("サーバーイベントの連携を解除しました。")

        header = "\n".join(["### 変更しました", *notes])
        view = subscriptions_view([subscription_info(row, sub)], header=header)
        await interaction.followup.send(view=view, ephemeral=True)
        await bot.scheduler.process(sub.schedule_id)

    @app_commands.command(
        name="refresh", description="登録先から最新のスケジュールをすぐに取得します"
    )
    @app_commands.describe(schedule="スケジュール（省略すると登録済みのすべて）")
    @app_commands.autocomplete(schedule=schedule_autocomplete)
    async def refresh(self, interaction: discord.Interaction, schedule: str | None = None) -> None:
        bot = bot_of(interaction)
        guild_id = guild_of(interaction).id
        entries = (
            [find_entry(bot, guild_id, schedule)] if schedule else guild_entries(bot, guild_id)
        )
        if not entries:
            raise UserError("登録されたスケジュールはありません。")
        await interaction.response.defer(ephemeral=True, thinking=True)
        labels = {
            FetchOutcome.UPDATED: "更新がありました",
            FetchOutcome.UNCHANGED: "変更はありません",
            FetchOutcome.FAILED: "取得できませんでした",
        }
        lines = []
        for sub, row in entries:
            outcome = await bot.scheduler.process(sub.schedule_id, force_fetch=True)
            label = labels[outcome] if outcome else "取得できませんでした"
            lines.append(f"- {display_name(row.event_name, row.schedule)}: {label}")
        await interaction.followup.send("\n".join(lines), ephemeral=True)
