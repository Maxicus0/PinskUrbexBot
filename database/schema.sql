-- schema.sql — полная схема БД PostgreSQL.
-- Выполняется через database/init_db.py при каждом старте бота
-- (CREATE TABLE IF NOT EXISTS — безопасно запускать повторно).
--
-- С релиза 0.4 колонки, идентифицирующие человека (telegram_id и всё, что
-- на него ссылается, плюс username/full_name/текст заметок админа), имеют
-- тип BYTEA, а не BIGINT/TEXT — это зашифрованные значения (см.
-- utils/crypto.py), не сырые telegram id и не читаемый текст. Читать и
-- писать их напрямую SQL-запросом бессмысленно — всегда через
-- database/*_repo.py, которые шифруют/расшифровывают прозрачно. Базы,
-- заведённые до 0.4 (там эти колонки ещё BIGINT/TEXT), мигрируются
-- автоматически при первом запуске на новой версии — см.
-- database/init_db.py, _migrate_v04_encrypt_pii.

CREATE TABLE IF NOT EXISTS users (
    telegram_id BYTEA PRIMARY KEY,      -- зашифрован (utils.crypto.encrypt_id), детерминированно
    username    BYTEA,                  -- зашифрован (utils.crypto.encrypt_text)
    full_name   BYTEA,                  -- зашифрован (utils.crypto.encrypt_text)
    credits     INTEGER NOT NULL DEFAULT 0,
    archive_display_mode TEXT NOT NULL DEFAULT 'standard', -- standard|danger_color, см. /settings, config.ARCHIVE_DISPLAY_MODES
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
    created_by     BYTEA REFERENCES users(telegram_id), -- зашифрован (utils.crypto.encrypt_id)
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
--
-- С релиза 0.4 это ТОЛЬКО очередь на модерацию, не постоянный архив: строка
-- живёт тут, пока status='pending', и удаляется целиком (database.insights_
-- repo.delete_insight) сразу же, как только админ доводит её обработку до
-- конца — см. handlers/admin_rate_insight.py. Поэтому status здесь на
-- практике всегда 'pending' (иных значений в текущей логике никто не
-- присваивает), а credits_awarded/rated_by/rated_at не заполняются вовсе —
-- оставлены только ради обратной совместимости со старыми базами, где такие
-- строки могли накопиться до 0.4.
CREATE TABLE IF NOT EXISTS insights (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             BYTEA NOT NULL REFERENCES users(telegram_id), -- зашифрован (utils.crypto.encrypt_id)
    type                TEXT NOT NULL DEFAULT 'insight',
    related_object_id   BIGINT REFERENCES objects(id),   -- legacy, не используется новыми хендлерами
    related_object_name TEXT,                            -- legacy, не используется новыми хендлерами
    text                TEXT NOT NULL,
    photo_file_id       TEXT,                             -- legacy (одно фото); см. insight_media ниже
    status              TEXT NOT NULL DEFAULT 'pending',  -- legacy: см. комментарий выше, всегда 'pending'
    credits_awarded     INTEGER,                          -- legacy, не заполняется с 0.4
    rated_by            BIGINT,                           -- legacy, не заполняется с 0.4 (и не шифруется — мёртвая колонка)
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    rated_at            TIMESTAMPTZ                       -- legacy, не заполняется с 0.4
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
    user_id     BYTEA NOT NULL REFERENCES users(telegram_id), -- зашифрован (utils.crypto.encrypt_id)
    admin_id    BYTEA NOT NULL,                               -- зашифрован (utils.crypto.encrypt_id)
    text        BYTEA NOT NULL,                               -- зашифрован (utils.crypto.encrypt_text)
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Учёт отправленных праздничных рассылок (см. utils/holidays.py), чтобы не
-- продублировать поздравление, если бот перезапустится в тот же день.
CREATE TABLE IF NOT EXISTS holiday_broadcasts (
    holiday_date  DATE PRIMARY KEY,
    sent_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
