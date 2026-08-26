"""database/notes_repo.py — приватные заметки админов об авторах инсайдов
(user_notes). Сам автор заметку никогда не видит."""
from database.db import get_connection


def add_note(user_id: int, admin_id: int, text: str) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO user_notes (user_id, admin_id, text) VALUES (%s, %s, %s) RETURNING id",
            (user_id, admin_id, text),
        )
        return cur.fetchone()["id"]


def get_notes(user_id: int):
    """Все заметки об авторе, от новых к старым."""
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM user_notes WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()


def count_notes(user_id: int) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM user_notes WHERE user_id = %s", (user_id,)
        ).fetchone()
        return row["n"]
