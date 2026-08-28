"""database/holidays_repo.py — учёт того, за какие даты уже отправлена
праздничная рассылка (см. utils/holidays.py), чтобы не продублировать
поздравление, если бот перезапустится в тот же день."""
from datetime import date

from database.db import get_connection


def try_reserve_broadcast(holiday_date: date) -> bool:
    """Атомарно резервирует дату рассылки.

    True  — резерв наш, рассылку нужно отправить прямо сейчас.
    False — на эту дату рассылка уже была отправлена (или отправляется
            параллельно) — отправлять повторно не нужно.
    """
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO holiday_broadcasts (holiday_date) VALUES (%s) "
            "ON CONFLICT (holiday_date) DO NOTHING RETURNING holiday_date",
            (holiday_date,),
        )
        return cur.fetchone() is not None
