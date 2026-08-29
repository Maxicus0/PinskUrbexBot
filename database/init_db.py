"""
database/init_db.py
---------------------
Создаёт таблицы по schema.sql, если их ещё нет, и добавляет недостающие
колонки на уже существующей базе через ADD COLUMN IF NOT EXISTS.

Вызывается один раз при старте бота (bot.py). Безопасно запускать повторно.
Можно запустить и отдельно: python -m database.init_db
"""
from pathlib import Path

from database.db import get_connection

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

# Колонки, которые могли отсутствовать в базах, созданных до появления
# соответствующей фичи. Формат: {таблица: [(колонка, DDL-определение), ...]}
_REQUIRED_COLUMNS: dict[str, list[tuple[str, str]]] = {
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


def ensure_schema() -> None:
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_connection() as conn:
        conn.executescript(schema_sql)
        _ensure_columns(conn)


if __name__ == "__main__":
    ensure_schema()
    print("База данных готова.")
