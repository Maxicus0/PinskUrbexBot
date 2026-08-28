"""
database/db.py
---------------
Единственное место, где открывается соединение с PostgreSQL.

Пул соединений создаётся один раз (psycopg2.pool), get_connection()
выдаёт обёртку с sqlite-подобным .execute()/.executescript(), чтобы
репозитории в этой папке не менялись сверх необходимого.

Оптимизация под Render free: бесплатный Web Service засыпает после ~15 минут
простоя, а бесплатные/дешёвые Postgres (в т.ч. Neon, на который указывает
render.yaml через fromDatabase) сами закрывают простаивающие соединения ещё
раньше. Соединение, которое пролежало в пуле всё это время, к моменту
пробуждения бота обычно уже мертво — первый же запрос падает с
OperationalError/InterfaceError. get_connection() один раз "пингует"
выданное из пула соединение и, если оно протухло, пересоздаёт пул и пробует
снова — без этого любое обращение к БД после сна инстанса роняло бы хендлер.
"""
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from psycopg2.pool import SimpleConnectionPool

import config

_pool: SimpleConnectionPool | None = None

_STALE_CONNECTION_ERRORS = (psycopg2.OperationalError, psycopg2.InterfaceError)


def _get_pool() -> SimpleConnectionPool:
    global _pool
    if _pool is None:
        _pool = SimpleConnectionPool(1, 10, dsn=config.DATABASE_URL)
    return _pool


def _reset_pool() -> None:
    """Закрывает и выбрасывает текущий пул целиком — используется, когда в
    нём обнаружилось протухшее соединение: остальные, скорее всего, тоже под
    вопросом (все они простаивали одинаково долго), дешевле пересоздать пул,
    чем проверять каждое соединение по отдельности."""
    global _pool
    if _pool is not None:
        try:
            _pool.closeall()
        except Exception:
            pass
    _pool = None


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
    conn = None
    for attempt in (1, 2):
        pool = _get_pool()
        conn = pool.getconn()
        try:
            with conn.cursor() as ping_cur:
                ping_cur.execute("SELECT 1")
            break
        except _STALE_CONNECTION_ERRORS:
            try:
                conn.close()
            except Exception:
                pass
            _reset_pool()
            if attempt == 2:
                raise
            conn = None

    try:
        yield _ConnWrapper(conn)
        conn.commit()
    except _STALE_CONNECTION_ERRORS:
        # Соединение умерло между пингом и запросом (редко, но возможно) —
        # само оно уже не годится для пула.
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
