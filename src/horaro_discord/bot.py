from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

import aiohttp
import discord
from discord import app_commands

from .horaro import HoraroClient
from .rij import RijClient
from .schedule import Schedule
from .scheduler import Notification, Scheduler
from .store import Store
from .timeline import server_event_times
from .views import clip, notification_view

log = logging.getLogger(__name__)

_SENDABLE = (discord.TextChannel, discord.VoiceChannel, discord.Thread)


def utc(t: int) -> datetime:
    return datetime.fromtimestamp(t, UTC)


class DiscordAdapter:
    """Implements the scheduler's DiscordPort, plus server event creation for commands."""

    def __init__(self, client: discord.Client) -> None:
        self.client = client

    async def _channel(
        self, channel_id: int
    ) -> discord.TextChannel | discord.VoiceChannel | discord.Thread | None:
        channel = self.client.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.client.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden):
                return None
        return channel if isinstance(channel, _SENDABLE) else None

    async def send(self, channel_id: int, notification: Notification) -> int | None:
        channel = await self._channel(channel_id)
        if channel is None:
            log.warning("Channel %s is unavailable; notification dropped", channel_id)
            return None
        try:
            message = await channel.send(
                view=notification_view(notification),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (discord.Forbidden, discord.NotFound) as e:
            log.warning("Cannot send to channel %s; notification dropped: %s", channel_id, e)
            return None
        return message.id

    async def edit(self, channel_id: int, message_id: int, notification: Notification) -> None:
        channel = await self._channel(channel_id)
        if channel is None:
            return
        try:
            await channel.get_partial_message(message_id).edit(
                view=notification_view(notification),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (discord.Forbidden, discord.NotFound) as e:
            log.warning("Cannot edit message %s in channel %s: %s", message_id, channel_id, e)

    async def _event(self, guild: discord.Guild, event_id: int) -> discord.ScheduledEvent | None:
        event = guild.get_scheduled_event(event_id)
        if event is None:
            try:
                event = await guild.fetch_scheduled_event(event_id)
            except discord.NotFound:
                return None
        return event

    async def sync_server_event(
        self, guild_id: int, event_id: int, start_t: int, end_t: int
    ) -> bool:
        guild = self.client.get_guild(guild_id)
        if guild is None:
            # Unavailable for now, or the bot left the guild: keep the link either way.
            return True
        event = await self._event(guild, event_id)
        if event is None or event.status in (
            discord.EventStatus.ended,
            discord.EventStatus.cancelled,
        ):
            return False
        now = discord.utils.utcnow()
        start, end = utc(start_t), utc(end_t)
        # Discord only accepts future start times, and only before the event becomes active.
        move_start = (
            event.status is discord.EventStatus.scheduled
            and event.start_time != start
            and start > now + timedelta(minutes=1)
        )
        move_end = event.end_time != end and end > max(
            now, start if move_start else event.start_time
        )
        if move_start and move_end:
            await event.edit(start_time=start, end_time=end)
        elif move_start:
            await event.edit(start_time=start)
        elif move_end:
            await event.edit(end_time=end)
        else:
            return True
        log.info("Moved server event %s to %s - %s", event_id, start, end)
        return True

    async def create_server_event(
        self, guild: discord.Guild, name: str, schedule: Schedule
    ) -> discord.ScheduledEvent:
        start_t, end_t = server_event_times(schedule)
        return await guild.create_scheduled_event(
            name=clip(name, 100),
            start_time=utc(start_t),
            end_time=utc(end_t),
            entity_type=discord.EntityType.external,
            privacy_level=discord.PrivacyLevel.guild_only,
            location=clip(schedule.link, 100),
            description=f"{schedule.link}\nスケジュールに合わせて自動で更新されます。",
        )

    async def delete_server_event(self, guild_id: int, event_id: int) -> None:
        """Delete the event if it has not started; started events are left as they are."""
        guild = self.client.get_guild(guild_id)
        event = await self._event(guild, event_id) if guild else None
        if event is not None and event.status is discord.EventStatus.scheduled:
            await event.delete()


class HoraroBot(discord.Client):
    def __init__(self, store: Store, session: aiohttp.ClientSession) -> None:
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)
        self.store = store
        self.horaro = HoraroClient(session)
        self.rij = RijClient(session)
        self.adapter = DiscordAdapter(self)
        self.scheduler = Scheduler(store, self.horaro, self.adapter, rij=self.rij)
        self._scheduler_task: asyncio.Task[None] | None = None

    async def setup_hook(self) -> None:
        from .commands import AdminGroup, HoraroGroup

        self.tree.add_command(HoraroGroup())
        self.tree.add_command(AdminGroup())
        await self.tree.sync()
        self._scheduler_task = asyncio.create_task(self._run_scheduler())

    async def _run_scheduler(self) -> None:
        await self.wait_until_ready()
        log.info("Scheduler started")
        await self.scheduler.run()

    async def close(self) -> None:
        if self._scheduler_task:
            self._scheduler_task.cancel()
        await super().close()
