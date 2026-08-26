-- schema.sql — полная схема БД PostgreSQL.
-- Выполняется через database/init_db.py при каждом старте бота
-- (CREATE TABLE IF NOT EXISTS — безопасно запускать повторно).

CREATE TABLE IF NOT EXISTS users (
    telegram_id BIGINT PRIMARY KEY,
    username    TEXT,
    full_name   TEXT,
    credits     INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Объекты архива (заброшки).
CREATE TABLE IF NOT EXISTS objects (
    id             BIGSERIAL PRIMARY KEY,
    title          TEXT NOT NULL,
    history        TEXT,
    current_state  TEXT,
    rumors         TEXT,
    coordinates    TEXT,                               -- DMS из Google Maps, напр. 52°07'56.1"N 26°01'02.5"E
    min_credits    INTEGER NOT NULL DEFAULT 0,          -- порог доверия для доступа к карточке
    status         TEXT NOT NULL DEFAULT 'published',   -- published | draft
    created_by     BIGINT REFERENCES users(telegram_id),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- kind различает фото объекта и фото точки входа ("залаза").
CREATE TABLE IF NOT EXISTS object_photos (
    id         BIGSERIAL PRIMARY KEY,
    object_id  BIGINT NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
    file_id    TEXT NOT NULL,                       -- telegram file_id, файл не хранится локально
    kind       TEXT NOT NULL DEFAULT 'object',       -- object | entry
    caption    TEXT,
    added_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Инсайды пользователей (свободный текст + опциональное фото).
CREATE TABLE IF NOT EXISTS insights (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             BIGINT NOT NULL REFERENCES users(telegram_id),
    type                TEXT NOT NULL DEFAULT 'insight',
    related_object_id   BIGINT REFERENCES objects(id),   -- legacy, не используется новыми хендлерами
    related_object_name TEXT,                            -- legacy, не используется новыми хендлерами
    text                TEXT NOT NULL,
    photo_file_id       TEXT,
    status              TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | rejected
    credits_awarded     INTEGER,
    rated_by            BIGINT,                           -- telegram_id админа, оценившего инсайд
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    rated_at            TIMESTAMPTZ
);

-- Приватные заметки админов об авторах инсайдов (сам автор их не видит).
CREATE TABLE IF NOT EXISTS user_notes (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(telegram_id),
    admin_id    BIGINT NOT NULL,
    text        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
