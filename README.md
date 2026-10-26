# Horaro Discord Bot

A Discord bot that announces each program of a [Horaro](https://horaro.net) or [RTA in Japan official](https://rtain.jp/schedule/) schedule in a channel shortly before it starts.

[日本語](README.ja.md)

The bot's messages and command descriptions are in Japanese.

## Features

- Notifies a channel a set number of minutes before each program starts.
- Follows schedule changes made by the organizers.
  - During an event, the registered schedule source is checked every minute.
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
| `/horaro-admin refresh [schedule]` | Fetch the latest schedule from its source now |

- `url` takes a Horaro URL such as `https://horaro.net/event/schedule` or an official RiJ URL such as `https://rtain.jp/schedule/?event=rtaijw2026`. The source is detected automatically.
  - With a Horaro event URL, you pick the schedule from a menu.
  - Typing an event name suggests matching official RiJ and Horaro events, labeled by source.
  - horaro.org URLs are accepted and read from horaro.net.
- `notice` is how many minutes before the start to notify (default 10).
- `key_column` is the column used as the notification title. It also identifies programs, so pick a column that rarely changes, such as the game name. A game-like column is chosen automatically on registration.
- `server_event` creates a Discord server event. It cannot be created for a schedule that has already started.

For example, register an official RiJ schedule with the same command used for Horaro:

```text
/horaro-admin add url:https://rtain.jp/schedule/?event=rtaijw2026
```

## Setup

Requires [uv](https://docs.astral.sh/uv/).

1. Clone the repository and install the dependencies.

   ```sh
   git clone https://github.com/drago-suzuki58/Horaro-Discord.git
   cd Horaro-Discord
   uv sync --no-dev
   ```

2. Create an application with **New Application** in the [Discord Developer Portal](https://discord.com/developers/applications), then configure it as follows:

   - **General Information**: Copy the **Application ID**. This is the `CLIENT_ID` in the invite URL.
   - **Bot**: Obtain a bot token, using **Reset Token** if needed. Set it as `DISCORD_TOKEN` in `.env` later. This is not the Client Secret or Public Key. Never publish or share the token.
   - **Bot → Privileged Gateway Intents**: Leave **Presence Intent**, **Server Members Intent** and **Message Content Intent** all **OFF**.
   - **Bot → Requires OAuth2 Code Grant**: Set this to **OFF**. This bot does not implement an OAuth2 callback.
   - **Installation → Installation Contexts**: Enable **Guild Install**. **User Install** is not needed; commands work only inside servers.
   - **Installation → Default Install Settings → Guild Install**: Select the `bot` and `applications.commands` scopes, and only the permissions needed below. Use the same selections if using **OAuth2 → URL Generator** instead.
   - **General Information → Interactions Endpoint URL**: Leave this blank. Commands are received over the Gateway, so no public HTTP server or redirect URL is needed.

   Enable **Bot → Public Bot** only if other users should be able to invite the bot. It is unnecessary if you invite and operate it yourself.

3. Invite the bot with the following URL, replacing `CLIENT_ID` with the Application ID. The user inviting it needs **Manage Server** in the destination server.

    ```
    https://discord.com/oauth2/authorize?client_id=CLIENT_ID&scope=bot+applications.commands&permissions=17867063954432&integration_type=0
    ```

   This URL requests View Channels, Send Messages, Send Messages in Threads and Create Events. For notifications in regular text channels only, change it to `permissions=3072`.

4. Copy `.env.example` to `.env` and set `DISCORD_TOKEN`.

5. Start the bot.

   ```sh
   uv run horaro-discord
   ```

Registrations and sent notifications are stored in `DATABASE_PATH` (default `data/horaro-discord.db`).

Before updating, stop the bot and back up the database. Existing databases are migrated automatically at startup, preserving registrations and notification history. Existing Horaro registrations are not switched to the official RiJ site automatically: register the new URL and remove the old registration if it is no longer needed.

### Bot permissions

Bot permissions and the permissions of users running commands are separate. **The bot does not need Administrator.**

| Permission | When required | Purpose |
|---|---|---|
| View Channels | Required | Access the notification channel |
| Send Messages | Required for notifications in regular channels | Post program notifications |
| Send Messages in Threads | Only for notifications in threads | Post notifications inside threads |
| Create Events | Only when using `server_event:true` | Create server events, update their planned times and delete them before they start; only events created by the bot are managed |

You can change `permissions` in the invite URL to match the features you use:

| Features | `permissions` value |
|---|---|
| Notifications in regular text channels only | `3072` |
| Regular notifications and server event integration | `17592186047488` |
| Regular notifications, thread notifications and server event integration | `17867063954432` |

- View Channels and Send Messages must be allowed **in the actual notification channel**, not just on the server role. Check private-channel and category permission overrides.
- To use a thread as the notification destination, run `/horaro-admin add` inside it and omit `channel`. The bot needs access to the parent channel and permission to send in threads. Add the bot to private threads and unlock locked threads. The bot does not create or manage threads.
- Server events use an external URL as their location. Grant Create Events **on the server role**. Connect, Speak and Manage Events are not needed; the bot operates only on events it created.
- Read Message History and Manage Messages are not needed. Notifications are edited using message IDs saved in the database, and only the bot's own messages are edited.
- Embed Links and Attach Files are not needed. Current messages use text and buttons in Components V2 layouts, not embeds or attachments.
- The bot does not need Manage Server, Manage Roles, Manage Channels or Manage Webhooks.

See Discord's official [permission reference](https://docs.discord.com/developers/topics/permissions) and [scheduled event permission requirements](https://docs.discord.com/developers/resources/guild-scheduled-event#guild-scheduled-event-permissions-requirements) for details.

### Permissions for users running commands

- Users need View Channels and Use Application Commands in the channel where they run commands.
- Regular members can use `/horaro`.
- `/horaro-admin` requires Manage Server by default. To change access for users, roles or channels, go to **Server Settings → Integrations → this bot**. This is a user permission, not a permission the bot itself needs.

Commands are registered automatically when the bot starts. If they do not appear, check that the bot is installed to the server and that the user has permission to use commands. If only scheduled notifications are missing, check the bot's permissions in the notification channel.

## Notes

- Notifications follow planned times at the registered source. Delays are reflected only after the organizers update the published schedule.
- Official RiJ schedules use public JSON schema version 2. Start times are calculated from the event start plus each preceding run's estimate and setup time. Unsupported schema versions are treated as fetch failures; the last successfully fetched schedule remains in use.
- Only horaro.net (including horaro.org URLs) and `rtain.jp/schedule/` are supported. Arbitrary self-hosted Horaro instances and custom JSON formats cannot be registered.
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
