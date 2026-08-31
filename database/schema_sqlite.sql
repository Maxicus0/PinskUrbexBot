-- schema_sqlite.sql — схема БД для бета-бота (SQLite), см. database/db.py.
-- Аналог schema.sql (PostgreSQL), но без миграций: бета-база всегда
-- создаётся с нуля уже в актуальном виде, поэтому колонки, которые в
-- Postgres добавлялись поздними ALTER TABLE (database/init_db.py), здесь
-- сразу часть исходных CREATE TABLE.

CREATE TABLE IF NOT EXISTS users (
    telegram_id BLOB PRIMARY KEY,        -- зашифрован (utils.crypto.encrypt_id)
    username    BLOB,                    -- зашифрован (utils.crypto.encrypt_text)
    full_name   BLOB,                    -- зашифрован (utils.crypto.encrypt_text)
    credits     INTEGER NOT NULL DEFAULT 0,
    archive_display_mode TEXT NOT NULL DEFAULT 'standard',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS objects (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    title          TEXT NOT NULL,
    history        TEXT,
    current_state  TEXT,
    rumors         TEXT,
    coordinates    TEXT,
    min_credits    INTEGER NOT NULL DEFAULT 0,
    danger_level   TEXT NOT NULL DEFAULT 'black',
    status         TEXT NOT NULL DEFAULT 'published',
    created_by     BLOB REFERENCES users(telegram_id),
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS object_photos (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    object_id  INTEGER NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
    file_id    TEXT NOT NULL,
    kind       TEXT NOT NULL DEFAULT 'object',
    caption    TEXT,
    added_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS insights (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             BLOB NOT NULL REFERENCES users(telegram_id),
    type                TEXT NOT NULL DEFAULT 'insight',
    related_object_id   INTEGER REFERENCES objects(id),
    related_object_name TEXT,
    text                TEXT NOT NULL,
    photo_file_id       TEXT,
    status              TEXT NOT NULL DEFAULT 'pending',
    credits_awarded     INTEGER,
    rated_by            INTEGER,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    rated_at            TEXT
);

CREATE TABLE IF NOT EXISTS insight_media (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    insight_id  INTEGER NOT NULL REFERENCES insights(id) ON DELETE CASCADE,
    file_id     TEXT NOT NULL,
    media_type  TEXT NOT NULL DEFAULT 'photo',
    added_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     BLOB NOT NULL REFERENCES users(telegram_id),
    admin_id    BLOB NOT NULL,
    text        BLOB NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS holiday_broadcasts (
    holiday_date  TEXT PRIMARY KEY,
    sent_at       TEXT NOT NULL DEFAULT (datetime('now'))
);
