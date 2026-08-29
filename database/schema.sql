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
    danger_level   TEXT NOT NULL DEFAULT 'black',       -- white|green|yellow|red|black, см. config.DANGER_LEVELS
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

-- Инсайды пользователей (свободный текст + опциональные медиа).
CREATE TABLE IF NOT EXISTS insights (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             BIGINT NOT NULL REFERENCES users(telegram_id),
    type                TEXT NOT NULL DEFAULT 'insight',
    related_object_id   BIGINT REFERENCES objects(id),   -- legacy, не используется новыми хендлерами
    related_object_name TEXT,                            -- legacy, не используется новыми хендлерами
    text                TEXT NOT NULL,
    photo_file_id       TEXT,                             -- legacy (одно фото); см. insight_media ниже
    status              TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | rejected
    credits_awarded     INTEGER,
    rated_by            BIGINT,                           -- telegram_id админа, оценившего инсайд
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    rated_at            TIMESTAMPTZ
);

-- Медиафайлы инсайда (фото и/или видео), до config.MAX_INSIGHT_MEDIA штук на
-- инсайд (проверяется в handlers/insight_submit.py на этапе сбора, до
-- вставки в БД). Как и object_photos, хранит только telegram file_id — сам
-- файл целиком остаётся на серверах Telegram, бот его не скачивает и не
-- переносит к себе (подробнее — README, раздел "Безопасность и анонимность").
CREATE TABLE IF NOT EXISTS insight_media (
    id          BIGSERIAL PRIMARY KEY,
    insight_id  BIGINT NOT NULL REFERENCES insights(id) ON DELETE CASCADE,
    file_id     TEXT NOT NULL,
    media_type  TEXT NOT NULL DEFAULT 'photo',   -- photo | video
    added_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Приватные заметки админов об авторах инсайдов (сам автор их не видит).
CREATE TABLE IF NOT EXISTS user_notes (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(telegram_id),
    admin_id    BIGINT NOT NULL,
    text        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Учёт отправленных праздничных рассылок (см. utils/holidays.py), чтобы не
-- продублировать поздравление, если бот перезапустится в тот же день.
CREATE TABLE IF NOT EXISTS holiday_broadcasts (
    holiday_date  DATE PRIMARY KEY,
    sent_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
