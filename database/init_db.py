"""
database/init_db.py
---------------------
Создаёт таблицы по schema.sql, если их ещё нет, и добавляет недостающие
колонки на уже существующей базе через ADD COLUMN IF NOT EXISTS.

Вызывается один раз при старте бота (bot.py). Безопасно запускать повторно.
Можно запустить и отдельно: python -m database.init_db
"""
import logging
from pathlib import Path

import config
from database.db import get_connection
from utils import crypto

logger = logging.getLogger(__name__)

_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = _DIR / "schema.sql"

# Колонки, которые могли отсутствовать в базах, созданных до появления
# соответствующей фичи. Формат: {таблица: [(колонка, DDL-определение), ...]}
_REQUIRED_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "users": [("archive_display_mode", "TEXT NOT NULL DEFAULT 'standard'")],
    "objects": [
        ("coordinates", "TEXT"),
        ("danger_level", "TEXT NOT NULL DEFAULT 'black'"),
    ],
    "object_photos": [("kind", "TEXT NOT NULL DEFAULT 'object'")],
    "insights": [("type", "TEXT NOT NULL DEFAULT 'insight'")],
}


def _ensure_columns(conn) -> None:
    for table, columns in _REQUIRED_COLUMNS.items():
        for column, ddl in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl}")


def _purge_legacy_rated_insights(conn) -> None:
    """Миграция 0.3 -> 0.4: разовая уборка мусора, накопленного ДО 0.4.

    До 0.4 database.insights_repo.set_insight_rated() делал UPDATE и
    навсегда оставлял в insights каждый уже оценённый инсайд со
    status='approved'/'rejected' (текст, медиа-связи, всё). С 0.4 таблица
    insights — это ТОЛЬКО очередь на модерацию: строка живёт, пока
    status='pending', и удаляется целиком через delete_insight() сразу же,
    как только админ доводит её обработку до конца (см. database/
    insights_repo.py). Поэтому у баз, заведённых ещё на 0.1-0.3, здесь
    могла годами копиться история уже разобранных инсайдов — она никому не
    нужна и просто занимает место (актуально для тарифов PostgreSQL с
    лимитом объёма, см. README, раздел «Деплой на Render»), плюс хранит
    больше личных данных, чем необходимо.

    Удаляем всё, что не 'pending', при каждом старте — insight_media
    уходит каскадно (ON DELETE CASCADE в schema.sql), отдельный запрос не
    нужен. На базе, которая уже прошла через 0.4 (где ничего, кроме
    'pending', в принципе не появляется), это no-op.
    """
    conn.execute("DELETE FROM insights WHERE status != 'pending'")


# Колонки, которые с 0.4 хранят зашифрованные персональные данные (см.
# utils/crypto.py и комментарии в schema.sql), а раньше (0.1-0.3) были
# обычными BIGINT/TEXT. Формат одной записи:
#   (таблица, колонка, "как найти строку снова при UPDATE", шифрующая
#    функция, обязана ли колонка быть NOT NULL после миграции)
#
# row_key — это либо telegram_id (для самой users — так как эта таблица
# ссылается сама на себя: её собственный PK и есть шифруемая колонка), либо
# id — суррогатный PK самой таблицы (objects/insights/user_notes). Важно:
# row_key ищет строку по ЕЁ ТЕКУЩЕМУ значению на момент SELECT/UPDATE — если
# users.telegram_id к этому шагу уже мигрирован (стал bytea), это не мешает:
# для сопоставления строки неважно, зашифрован ключ поиска или нет, лишь бы
# он был уникален и не менялся между SELECT и UPDATE одной и той же колонки.
_PII_MIGRATIONS: list[tuple[str, str, str, "callable", bool]] = [
    ("users", "telegram_id", "telegram_id", crypto.encrypt_id, True),
    ("users", "username", "telegram_id", crypto.encrypt_text, False),
    ("users", "full_name", "telegram_id", crypto.encrypt_text, False),
    ("objects", "created_by", "id", crypto.encrypt_id, False),
    ("insights", "user_id", "id", crypto.encrypt_id, True),
    ("user_notes", "user_id", "id", crypto.encrypt_id, True),
    ("user_notes", "admin_id", "id", crypto.encrypt_id, True),
    ("user_notes", "text", "id", crypto.encrypt_text, True),
]


def _column_type(conn, table: str, column: str) -> str | None:
    row = conn.execute(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s",
        (table, column),
    ).fetchone()
    return row["data_type"] if row else None


def _migrate_one_pii_column(conn, table: str, column: str, row_key: str, encrypt, not_null: bool) -> None:
    """Переносит одну колонку в зашифрованный bytea "на живую", без внешних
    инструментов: заводит временную колонку рядом со старой, построчно
    шифрует значения в Python (ключ и алгоритм — только в приложении, в базе
    их никогда не было и не будет), затем удаляет старую колонку и
    переименовывает новую на её место.

    DROP COLUMN ... CASCADE предвиден и безопасен: у telegram_id это разом
    снимает PRIMARY KEY и все FOREIGN KEY, ссылающиеся на него (у
    objects.created_by / insights.user_id / user_notes.user_id) — их
    заново навешивает _restore_users_constraints() после того, как все
    участвующие колонки перешли на bytea. У остальных колонок CASCADE — не
    более чем гарантия на случай, если что-то на них всё-таки ссылается;
    сами по себе они ни на кого не влияют.
    """
    enc_column = f"{column}__enc"
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {enc_column} BYTEA")

    rows = conn.execute(f"SELECT {row_key} AS _row_key, {column} AS _value FROM {table}").fetchall()
    for row in rows:
        conn.execute(
            f"UPDATE {table} SET {enc_column} = %s WHERE {row_key} = %s",
            (encrypt(row["_value"]), row["_row_key"]),
        )

    conn.execute(f"ALTER TABLE {table} DROP COLUMN {column} CASCADE")
    conn.execute(f"ALTER TABLE {table} RENAME COLUMN {enc_column} TO {column}")
    if not_null:
        conn.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET NOT NULL")


def _restore_users_constraints(conn) -> None:
    """PRIMARY KEY на users.telegram_id и внешние ключи на него были сняты
    каскадом при миграции колонки (см. _migrate_one_pii_column) — теперь,
    когда все участвующие колонки уже bytea, навешиваем их обратно."""
    conn.execute("ALTER TABLE users ADD PRIMARY KEY (telegram_id)")
    conn.execute(
        "ALTER TABLE objects ADD CONSTRAINT objects_created_by_fkey "
        "FOREIGN KEY (created_by) REFERENCES users(telegram_id)"
    )
    conn.execute(
        "ALTER TABLE insights ADD CONSTRAINT insights_user_id_fkey "
        "FOREIGN KEY (user_id) REFERENCES users(telegram_id)"
    )
    conn.execute(
        "ALTER TABLE user_notes ADD CONSTRAINT user_notes_user_id_fkey "
        "FOREIGN KEY (user_id) REFERENCES users(telegram_id)"
    )


def _migrate_v04_encrypt_pii(conn) -> None:
    """Миграция 0.3 -> 0.4: шифрует telegram_id и другую персональную
    информацию (username, full_name, текст заметок админа) на уровне
    колонок — см. module docstring utils/crypto.py.

    Идемпотентна и безопасна для повторного запуска: прогресс определяется
    по фактическому типу users.telegram_id в БД (bigint = ещё не
    мигрировано, bytea = уже готово), а не по номеру версии где-то
    отдельно. На свежей базе (создана уже с bytea-схемой из schema.sql)
    это no-op — заходит и сразу выходит.

    Выполняется целиком в одной транзакции (см. ensure_schema — весь блок
    внутри одного `with get_connection()`), поэтому в Postgres это
    транзакционный DDL: если что-то пойдёт не так на середине (например,
    оборвётся соединение), откатится всё разом — база останется в прежнем,
    полностью рабочем состоянии 0.3, и на следующий запуск бот просто
    попробует смигрировать снова, а не зависнет наполовину смешанной
    схемой.
    """
    if _column_type(conn, "users", "telegram_id") == "bytea":
        return  # уже мигрировано (или свежая база, сразу созданная на 0.4)

    logger.info(
        "Обнаружена база до 0.4 — шифрую telegram_id и персональные данные "
        "(users, objects.created_by, insights.user_id, user_notes)..."
    )
    for table, column, row_key, encrypt, not_null in _PII_MIGRATIONS:
        _migrate_one_pii_column(conn, table, column, row_key, encrypt, not_null)
    _restore_users_constraints(conn)
    logger.info("Миграция 0.4 завершена: персональные данные в БД зашифрованы.")


# Ключ для pg_advisory_lock ниже — произвольное фиксированное число, просто
# "адрес" этой миграции в общем для всей БД пространстве advisory-локов; не
# имеет отношения к id объектов/пользователей/чему-либо ещё.
_MIGRATION_LOCK_KEY = 733_200_401


def ensure_schema() -> None:
    if config.IS_BETA_MODE:
        # Бета-режим: локальная SQLite при каждом запуске стирается и
        # пересобирается заново из свежего снимка боевой PostgreSQL — см.
        # database/beta_sync.py. Своей отдельной миграционной истории у неё
        # нет и не нужно: она никогда не переживает между запусками.
        from database.beta_sync import rebuild_from_production

        rebuild_from_production()
        return

    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_connection() as conn:
        conn.executescript(schema_sql)
        _ensure_columns(conn)

        # Боевой и бета-бот (см. README, «Бета-бот для локального теста»)
        # могут стартовать на одной DATABASE_URL одновременно — например,
        # сразу после обновления пре-0.4 базы. Оба тогда в один момент
        # увидят "ещё не мигрировано" (см. _migrate_v04_encrypt_pii) и без
        # этого лока полезли бы в ALTER TABLE/DROP COLUMN параллельно, что
        # для DDL небезопасно. pg_advisory_lock сериализует миграцию между
        # процессами: второй просто дождётся, пока первый закоммитит, увидит
        # уже смигрированную схему и молча выйдет (no-op). Лочим только сам
        # миграционный шаг — CREATE TABLE IF NOT EXISTS и ADD COLUMN IF NOT
        # EXISTS выше и так безопасны при параллельном запуске.
        conn.execute("SELECT pg_advisory_lock(%s)", (_MIGRATION_LOCK_KEY,))
        try:
            _purge_legacy_rated_insights(conn)
            _migrate_v04_encrypt_pii(conn)
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (_MIGRATION_LOCK_KEY,))


if __name__ == "__main__":
    ensure_schema()
    print("База данных готова.")
