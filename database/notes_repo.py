"""database/notes_repo.py — приватные заметки админов об авторах инсайдов
(user_notes). Сам автор заметку никогда не видит.

С 0.4 user_id/admin_id/text хранятся зашифрованными (см. utils/crypto.py) —
шифрование/расшифровка происходит только здесь, вызывающий код работает с
обычными int/str."""
from database.db import get_connection
from utils import crypto


def _decrypt_note_row(row):
    row["user_id"] = crypto.decrypt_id(row["user_id"])
    row["admin_id"] = crypto.decrypt_id(row["admin_id"])
    row["text"] = crypto.decrypt_text(row["text"])
    return row


def add_note(user_id: int, admin_id: int, text: str) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO user_notes (user_id, admin_id, text) VALUES (%s, %s, %s) RETURNING id",
            (crypto.encrypt_id(user_id), crypto.encrypt_id(admin_id), crypto.encrypt_text(text)),
        )
        return cur.fetchone()["id"]


def get_notes(user_id: int):
    """Все заметки об авторе, от новых к старым."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM user_notes WHERE user_id = %s ORDER BY created_at DESC",
            (crypto.encrypt_id(user_id),),
        ).fetchall()
        return [_decrypt_note_row(row) for row in rows]


def count_notes(user_id: int) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM user_notes WHERE user_id = %s", (crypto.encrypt_id(user_id),)
        ).fetchone()
        return row["n"]
