"""
database/db.py
---------------
Единственное место, где открывается соединение с PostgreSQL.

Пул соединений создаётся один раз (psycopg2.pool), get_connection()
выдаёт обёртку с sqlite-подобным .execute()/.executescript(), чтобы
репозитории в этой папке не менялись сверх необходимого.
"""
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from psycopg2.pool import SimpleConnectionPool

import config

_pool: SimpleConnectionPool | None = None


def _get_pool() -> SimpleConnectionPool:
    global _pool
    if _pool is None:
        _pool = SimpleConnectionPool(1, 10, dsn=config.DATABASE_URL)
    return _pool


class _ConnWrapper:
    """Тонкая обёртка над psycopg2-соединением с execute()/executescript()."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, query: str, params: tuple = ()):
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(query, params)
        return cur

    def executescript(self, sql: str) -> None:
        cur = self._conn.cursor()
        cur.execute(sql)
        cur.close()


@contextmanager
def get_connection():
    conn = _get_pool().getconn()
    try:
        yield _ConnWrapper(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _get_pool().putconn(conn)
