"""
database/db.py
---------------
Единственное место, где открывается соединение с БД.

Боевой бот (BOT_TOKEN) → PostgreSQL, DATABASE_URL из .env, через пул
psycopg2. Бета-бот (BETA_BOT_TOKEN) → отдельный файл SQLite рядом с
проектом (config.BETA_DB_PATH), который при каждом запуске бота стирается
и пересобирается заново из свежего снимка той же PostgreSQL — см.
database/beta_sync.py. Своё содержимое между запусками он не хранит,
поэтому ломать его во время теста можно спокойно.

get_connection() выдаёт обёртку с execute()/executescript() — одинаковую
для обоих движков, поэтому database/*_repo.py не знают и не должны знать,
на чём сейчас работает бот.

Оптимизация под Render free (только PostgreSQL-путь): бесплатный Web
Service засыпает после ~15 минут простоя, а бесплатный/дешёвый Postgres сам
закрывает простаивающие соединения ещё раньше — get_connection() пингует
выданное из пула соединение и пересоздаёт пул, если оно протухло.

test_transaction() — для scripts/smoke_test.py: весь код внутри
`with test_transaction():` выполняется в одной транзакции, которая в конце
ВСЕГДА откатывается, что бы внутри ни случилось.
"""
import sqlite3
from contextlib import contextmanager
from contextvars import ContextVar

import psycopg2
import psycopg2.extras
from psycopg2.pool import SimpleConnectionPool

import config

_active_test_conn: ContextVar = ContextVar("_active_test_conn", default=None)


class _ConnWrapper:
    """execute()/executescript() поверх сырого соединения любого движка."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, query: str, params: tuple = ()):
        if config.IS_BETA_MODE:
            # %s → ? (psycopg2 → sqlite3 плейсхолдеры), NOW() → эквивалент
            # SQLite — единственные два postgres-изма, встречающиеся в SQL
            # из database/*_repo.py.
            query = query.replace("%s", "?").replace("NOW()", "CURRENT_TIMESTAMP")
            cur = self._conn.cursor()
            cur.execute(query, params)
        else:
            cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(query, params)
        return cur

    def executescript(self, sql: str) -> None:
        if config.IS_BETA_MODE:
            self._conn.executescript(sql)
        else:
            cur = self._conn.cursor()
            cur.execute(sql)
            cur.close()


# --- SQLite (бета-бот): одно соединение на процесс, файл рядом с проектом --- #

_sqlite_conn: sqlite3.Connection | None = None


def _sqlite_row(cursor, row) -> dict:
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


def _get_sqlite_connection() -> sqlite3.Connection:
    global _sqlite_conn
    if _sqlite_conn is None:
        _sqlite_conn = sqlite3.connect(config.BETA_DB_PATH, check_same_thread=False)
        _sqlite_conn.row_factory = _sqlite_row
        _sqlite_conn.execute("PRAGMA foreign_keys = ON")
    return _sqlite_conn


# --- PostgreSQL (боевой бот): пул соединений с проверкой на протухание --- #

_pool: SimpleConnectionPool | None = None
_STALE_CONNECTION_ERRORS = (psycopg2.OperationalError, psycopg2.InterfaceError)


def _get_pool() -> SimpleConnectionPool:
    global _pool
    if _pool is None:
        _pool = SimpleConnectionPool(1, 10, dsn=config.DATABASE_URL)
    return _pool


def _reset_pool() -> None:
    global _pool
    if _pool is not None:
        try:
            _pool.closeall()
        except Exception:
            pass
    _pool = None


def _acquire_pg_connection():
    for attempt in (1, 2):
        pool = _get_pool()
        conn = pool.getconn()
        try:
            with conn.cursor() as ping_cur:
                ping_cur.execute("SELECT 1")
            return conn
        except _STALE_CONNECTION_ERRORS:
            try:
                conn.close()
            except Exception:
                pass
            _reset_pool()
            if attempt == 2:
                raise
    return conn  # практически недостижимо


@contextmanager
def get_connection():
    active = _active_test_conn.get()
    if active is not None:
        yield active
        return

    if config.IS_BETA_MODE:
        conn = _get_sqlite_connection()
        try:
            yield _ConnWrapper(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return

    conn = _acquire_pg_connection()
    try:
        yield _ConnWrapper(conn)
        conn.commit()
    except _STALE_CONNECTION_ERRORS:
        try:
            conn.close()
        except Exception:
            pass
        _reset_pool()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        if conn is not None and not conn.closed:
            _get_pool().putconn(conn)


@contextmanager
def test_transaction():
    if config.IS_BETA_MODE:
        conn = _get_sqlite_connection()
        wrapper = _ConnWrapper(conn)
        token = _active_test_conn.set(wrapper)
        try:
            yield wrapper
        finally:
            _active_test_conn.reset(token)
            conn.rollback()
        return

    conn = _acquire_pg_connection()
    wrapper = _ConnWrapper(conn)
    token = _active_test_conn.set(wrapper)
    try:
        yield wrapper
    finally:
        _active_test_conn.reset(token)
        try:
            conn.rollback()
        finally:
            _get_pool().putconn(conn)
