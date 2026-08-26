"""
database/insights_repo.py
----------------------------
CRUD для инсайдов (свободных сообщений пользователей) и их модерации.
Поля type/related_object_* оставлены в схеме ради обратной совместимости
и не участвуют в текущей логике.
"""
from database.db import get_connection


def create_insight(user_id: int, text: str, photo_file_id: str | None) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO insights (user_id, text, photo_file_id) VALUES (%s, %s, %s) RETURNING id",
            (user_id, text, photo_file_id),
        )
        return cur.fetchone()["id"]


def get_insight(insight_id: int):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM insights WHERE id = %s", (insight_id,)
        ).fetchone()


def get_pending_insights():
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM insights WHERE status = 'pending' ORDER BY created_at"
        ).fetchall()


def set_insight_rated(insight_id: int, credits_awarded: int, rated_by: int) -> None:
    """0 кредитов = инсайд отклонён, >0 = одобрен."""
    status = "approved" if credits_awarded > 0 else "rejected"
    with get_connection() as conn:
        conn.execute(
            """UPDATE insights
               SET status = %s, credits_awarded = %s, rated_by = %s, rated_at = NOW()
               WHERE id = %s""",
            (status, credits_awarded, rated_by, insight_id),
        )
