"""Components V2 layouts. Times use Discord timestamp markup, shown in each viewer's timezone."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import discord
from discord import ui

from .schedule import Item, Schedule
from .scheduler import Kind, Notification
from .timeline import item_title, now_next

COLORS = {
    Kind.NOTICE: 0x3B82F6,
    Kind.RENOTICE: 0xF59E0B,
    Kind.CHANGED: 0xF59E0B,
    Kind.REMOVED: 0x6B7280,
}
INFO_COLOR = 0x3B82F6
# Discord allows 4000 characters of text per message in total.
MAX_VALUE = 200
MAX_TEXT = 3500


def ts(t: int, style: str) -> str:
    return f"<t:{t}:{style}>"


def clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def length(seconds: int) -> str:
    h, rest = divmod(seconds, 3600)
    return f"{h}:{rest // 60:02}:{rest % 60:02}"


def link_button(url: str) -> ui.Button[ui.LayoutView]:
    return ui.Button(style=discord.ButtonStyle.link, label="Horaro", url=url)


def text_view(text: str) -> ui.LayoutView:
    view = ui.LayoutView(timeout=None)
    view.add_item(ui.TextDisplay(text))
    return view


def notification_view(n: Notification) -> ui.LayoutView:
    title = clip(n.title, MAX_VALUE)
    lines = [f"-# {clip(n.schedule_name, MAX_VALUE)}"]
    if n.kind is Kind.REMOVED:
        lines += [
            f"### ~~{title}~~",
            f"スケジュールから削除されました（予定していた開始 {ts(n.scheduled_t, 't')}）",
        ]
    else:
        lines.append(f"### {title}")
        if n.kind is Kind.CHANGED and n.previous_t is not None:
            lines.append(
                f"**予定変更** ~~{ts(n.previous_t, 't')}~~ → "
                f"{ts(n.scheduled_t, 't')}（{ts(n.scheduled_t, 'R')}）"
            )
        else:
            lines.append(f"開始予定 {ts(n.scheduled_t, 't')}（{ts(n.scheduled_t, 'R')}）")
        if n.kind is Kind.RENOTICE and n.previous_t is not None:
            lines.append(f"**予定変更** 変更前の開始予定 ~~{ts(n.previous_t, 't')}~~")

    container: ui.Container[ui.LayoutView] = ui.Container(accent_colour=COLORS[n.kind])
    container.add_item(ui.Section("\n".join(lines), accessory=link_button(n.link)))
    details = [f"**{clip(c, 50)}**: {clip(v, MAX_VALUE)}" for c, v in n.details]
    if n.length_t is not None and n.kind is not Kind.REMOVED:
        details.append(f"**予定時間**: {length(n.length_t)}")
    if details:
        container.add_item(ui.TextDisplay(clip_lines(details, MAX_TEXT)))
    view = ui.LayoutView(timeout=None)
    view.add_item(container)
    return view


def clip_lines(lines: Sequence[str], limit: int) -> str:
    out: list[str] = []
    used = 0
    for line in lines:
        if used + len(line) + 1 > limit:
            out.append("…")
            break
        out.append(line)
        used += len(line) + 1
    return "\n".join(out)


@dataclass(frozen=True)
class ScheduleInfo:
    name: str
    schedule: Schedule
    key_column: str | None


def item_line(info: ScheduleInfo, item: Item) -> str:
    return clip(item_title(info.schedule, item, info.key_column), MAX_VALUE)


def status_lines(info: ScheduleInfo, now: int) -> list[str]:
    schedule = info.schedule
    lines = [f"### [{clip(info.name, MAX_VALUE)}]({schedule.link})"]
    if not schedule.items:
        return [*lines, "プログラムがありません"]
    if now < schedule.start_t:
        first = schedule.items[0]
        return [
            *lines,
            f"開始前（開始 {ts(schedule.start_t, 'f')}、{ts(schedule.start_t, 'R')}）",
            f"**最初**: {item_line(info, first)}",
        ]
    if now >= schedule.end_t:
        return [*lines, f"終了しました（{ts(schedule.end_t, 'f')}）"]
    state = now_next(schedule, now)
    current, nxt = state.current, state.next
    if current is None:
        lines.append("**現在**: 準備中")
    else:
        lines.append(
            f"**現在**: {item_line(info, current)}"
            f"（{ts(current.scheduled_t, 't')}〜{ts(current.end_t, 't')}）"
        )
    if nxt is not None:
        lines.append(f"**次**: {item_line(info, nxt)}（{ts(nxt.scheduled_t, 'R')}）")
    return lines


def now_view(infos: Sequence[ScheduleInfo], now: int) -> ui.LayoutView:
    view = ui.LayoutView(timeout=None)
    container: ui.Container[ui.LayoutView] = ui.Container(accent_colour=INFO_COLOR)
    for i, info in enumerate(infos):
        if i:
            container.add_item(ui.Separator())
        container.add_item(ui.TextDisplay("\n".join(status_lines(info, now))))
    view.add_item(container)
    return view


def upcoming_view(info: ScheduleInfo, items: Sequence[Item], now: int) -> ui.LayoutView:
    schedule = info.schedule
    header = f"### [{clip(info.name, MAX_VALUE)}]({schedule.link})\n今後のプログラム"
    lines = []
    for item in items:
        prefix = "**現在** " if item.scheduled_t <= now else ""
        details = " / ".join(
            clip(v, 60)
            for v in item.values
            if v and v.strip() and v.strip() != item_title(schedule, item, info.key_column)
        )
        line = f"{ts(item.scheduled_t, 't')} {prefix}**{item_line(info, item)}**"
        if details:
            line += f"\n-# {details}"
        lines.append(line)
    container: ui.Container[ui.LayoutView] = ui.Container(accent_colour=INFO_COLOR)
    container.add_item(ui.TextDisplay(header))
    container.add_item(ui.Separator())
    container.add_item(ui.TextDisplay(clip_lines(lines, MAX_TEXT) if lines else "ありません"))
    view = ui.LayoutView(timeout=None)
    view.add_item(container)
    return view


@dataclass(frozen=True)
class SubscriptionInfo:
    info: ScheduleInfo
    channel_id: int
    notice_minutes: int
    server_event: bool


def subscription_lines(s: SubscriptionInfo) -> list[str]:
    schedule = s.info.schedule
    return [
        f"### [{clip(s.info.name, MAX_VALUE)}]({schedule.link})",
        f"通知先: <#{s.channel_id}>（開始 {s.notice_minutes} 分前）",
        f"開始: {ts(schedule.start_t, 'f')} / 終了予定: {ts(schedule.end_t, 'f')}",
        f"見出しの列: {s.info.key_column or '（なし）'}",
        f"サーバーイベント: {'連携中' if s.server_event else 'なし'}",
    ]


def subscriptions_view(
    subs: Sequence[SubscriptionInfo], header: str | None = None
) -> ui.LayoutView:
    container: ui.Container[ui.LayoutView] = ui.Container(accent_colour=INFO_COLOR)
    if header:
        container.add_item(ui.TextDisplay(header))
    for i, s in enumerate(subs):
        if i or header:
            container.add_item(ui.Separator())
        container.add_item(ui.TextDisplay("\n".join(subscription_lines(s))))
    view = ui.LayoutView(timeout=None)
    view.add_item(container)
    return view
