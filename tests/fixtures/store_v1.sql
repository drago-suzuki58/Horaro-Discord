CREATE TABLE schedules (
    id TEXT PRIMARY KEY,
    event_name TEXT NOT NULL,
    payload TEXT NOT NULL,
    last_modified TEXT,
    fetched_at INTEGER NOT NULL,
    next_fetch_at INTEGER NOT NULL,
    failures INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE subscriptions (
    id INTEGER PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    schedule_id TEXT NOT NULL REFERENCES schedules (id),
    notice_minutes INTEGER NOT NULL,
    key_column TEXT,
    server_event_id INTEGER,
    UNIQUE (guild_id, schedule_id)
);
CREATE TABLE notifications (
    subscription_id INTEGER NOT NULL REFERENCES subscriptions (id) ON DELETE CASCADE,
    item_key TEXT NOT NULL,
    title TEXT NOT NULL,
    notified_t INTEGER NOT NULL,
    displayed_t INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    message_id INTEGER,
    removed INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (subscription_id, item_key)
);
PRAGMA user_version = 1;
