# Horaro Discord Bot

This bot is created to check the event schedule hosted on [Horaro](https://horaro.org) on Discord and enjoy the events with your friends.

Other Language LEADME  
[Japanese](README.ja.md)

## Features

- Register with Discord's event feature and notify the server
- Set reminders to prevent missing broadcasts
- Check the ongoing event program without leaving Discord

## Usage

Fork or clone this repository

```sh
git clone https://github.com/drago-suzuki58/Horaro-Discord.git
```

Install dependencies with pip or poetry

```sh
pip install -r requirements.txt
```

or

```sh
poetry install
```

Then, copy `.env.EXAMPLE` to `.env`, edit the contents such as tokens, and save it.

Once you are ready, run main.py to start the bot.

## Commands

- `/add_event`  
  Add a Horaro event from the entered URL.  
  You can specify the reminder time in minutes by adding `notice`.

- `/change_channel`  
  Change the channel for reminders of registered Horaro events.  
  Enter the URL of the relevant Horaro event and the channel ID (number) to change to.

- `/change_notice`  
  Change the reminder time for registered Horaro events.  
  Enter the URL of the relevant Horaro event and the new reminder time in minutes.

- `/change_url`  
  Change the reference URL of registered Horaro events.  
  Enter the old URL of the relevant Horaro event and the new URL.

- `/create_server_event`  
  Create a Discord server event from the URL of a registered Horaro event.  
  Enter the URL of the relevant Horaro event.

- `/create_server_event_all`  
  Create Discord server events in bulk from all registered Horaro events on the server where the command is executed.

- `/get_now_program`  
  Extract and display up to 10 ongoing programs from all registered Horaro events.

- `/list_events`  
  Display a list of Horaro events registered on the server where the command is executed.

- `/remove_event`  
  Remove the Horaro event that matches the specified URL from the registered events.  
  Includes a confirmation feature.

- `/update_schedule`  
  Update the data of Horaro events registered on the server to the latest information posted on Horaro in bulk.  
  By default, it automatically updates to the latest information every day, but manual updates are also possible if necessary.
