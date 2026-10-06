# Horaro Discord Bot

A Discord bot that announces each program of a [Horaro](https://horaro.net) schedule in a channel shortly before it starts.

[日本語](README.ja.md)

The bot's messages and command descriptions are in Japanese.

## Features

- Notifies a channel a set number of minutes before each program starts.
- Follows schedule changes made by the organizers.
  - During an event, Horaro is checked every minute.
  - When the start time of an announced program changes, the notification is edited to show the old and new times. If it moved by 5 minutes or more, the program is announced again at the new time.
  - Programs removed from the schedule are marked as removed in their notification.
- Shows the current, next and upcoming programs in Discord.
- Optionally creates a Discord server event for the schedule and keeps its start and end times up to date.

Times use Discord timestamps, so everyone sees them in their own timezone.

## Commands

Anyone can use `/horaro`. `/horaro-admin` requires the Manage Server permission by default (changeable under Server Settings > Integrations).

| Command | Description |
|---|---|
| `/horaro list` | Registered schedules |
| `/horaro now [schedule]` | Current and next program |
| `/horaro upcoming schedule [count]` | Upcoming programs (up to 10) |
| `/horaro-admin add url [channel] [notice] [server_event]` | Register a schedule |
| `/horaro-admin edit schedule [channel] [notice] [key_column] [server_event]` | Change a registration |
| `/horaro-admin remove schedule` | Unregister a schedule |
| `/horaro-admin refresh [schedule]` | Fetch the latest schedule from Horaro now |

- `url` takes a schedule URL such as `https://horaro.net/event/schedule`.
  - With an event URL, you pick the schedule from a menu.
  - Typing an event name suggests matching Horaro events.
  - horaro.org URLs are accepted and read from horaro.net.
- `notice` is how many minutes before the start to notify (default 10).
- `key_column` is the column used as the notification title. It also identifies programs, so pick a column that rarely changes, such as the game name. A game-like column is chosen automatically on registration.
- `server_event` creates a Discord server event. It cannot be created for a schedule that has already started.

## Setup

Requires [uv](https://docs.astral.sh/uv/).

1. Clone the repository and install the dependencies.

   ```sh
   git clone https://github.com/drago-suzuki58/Horaro-Discord.git
   cd Horaro-Discord
   uv sync --no-dev
   ```

2. Create an application and a bot in the [Discord Developer Portal](https://discord.com/developers/applications) and get its token. No privileged intents are needed.

3. Invite the bot with the following URL, replacing `CLIENT_ID` with your application ID.

   ```
   https://discord.com/oauth2/authorize?client_id=CLIENT_ID&scope=bot+applications.commands&permissions=17867063954432
   ```

   This grants View Channels, Send Messages, Send Messages in Threads and Create Events.

4. Copy `.env.example` to `.env` and set `DISCORD_TOKEN`.

5. Start the bot.

   ```sh
   uv run horaro-discord
   ```

Registrations and sent notifications are stored in `DATABASE_PATH` (default `data/horaro-discord.db`).

## Notes

- Notifications follow the planned times on Horaro. If the event runs late, this is reflected only after the organizers update the schedule on Horaro.
- Private schedules and hidden columns are not supported.
- Programs that started while the bot was offline are not announced after it restarts.
- horaro.org became a static archive in 2026, so data is read from the API of its successor, horaro.net.

## Development

```sh
uv sync
uv run pytest
uv run ruff check
uv run mypy
```
