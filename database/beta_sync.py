"""database/beta_sync.py — пересоздаёт локальную SQLite (beta.db) из
свежего снимка боевой PostgreSQL (config.DATABASE_URL). Вызывается сама
при каждом запуске бета-бота (config.IS_BETA_MODE, см. database/init_db.py
и bot.py) — локальная база каждый раз стирается и собирается заново, так
что бета-бот стартует уже на актуальных данных прода.

Персональные данные (utils/crypto.py) копируются как есть, зашифрованными
байтами, без расшифровки: раз APP_SECRET_KEY в .env — тот же, что и на
Render, шифротекст остаётся рабочим и в локальной SQLite, расшифровывать и
шифровать заново не нужно.

Источник (боевая PostgreSQL) открывается в транзакции READ ONLY и в конце
всегда откатывается — записать в неё отсюда физически нельзя, даже если в
этом модуле окажется баг.
"""
import sqlite3
from pathlib import Path

import psycopg2
import psycopg2.extras

import config

_SCHEMA_SQLITE_PATH = Path(__file__).resolve().parent / "schema_sqlite.sql"

# Порядок важен: сперва таблицы, на которые остальные ссылаются по FK.
_TABLES = (
    "users",
    "objects",
    "object_photos",
    "insights",
    "insight_media",
    "user_notes",
    "holiday_broadcasts",
)


def rebuild_from_production() -> None:
    pg_conn = psycopg2.connect(config.DATABASE_URL)
    pg_conn.set_session(readonly=True)
    try:
        _copy_all(pg_conn)
    finally:
        pg_conn.rollback()
        pg_conn.close()


def _copy_all(pg_conn) -> None:
    if config.BETA_DB_PATH.exists():
        config.BETA_DB_PATH.unlink()

    sqlite_conn = sqlite3.connect(config.BETA_DB_PATH)
    try:
        sqlite_conn.executescript(_SCHEMA_SQLITE_PATH.read_text(encoding="utf-8"))

        with pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as pg_cur:
            for table in _TABLES:
                pg_cur.execute(f"SELECT * FROM {table}")
                rows = pg_cur.fetchall()
                if not rows:
                    continue
                columns = list(rows[0].keys())
                placeholders = ", ".join("?" for _ in columns)
                sqlite_conn.executemany(
                    f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
                    [tuple(_to_sqlite(row[c]) for c in columns) for row in rows],
                )
                print(f"[OK] {table}: {len(rows)} строк")

        sqlite_conn.commit()
        print(f"[OK] beta.db пересоздана из снимка продакшена ({config.BETA_DB_PATH})")
    finally:
        sqlite_conn.close()


def _to_sqlite(value):
    """bytea из psycopg2 иногда приходит как memoryview — sqlite3 хочет bytes."""
    return bytes(value) if isinstance(value, memoryview) else value
