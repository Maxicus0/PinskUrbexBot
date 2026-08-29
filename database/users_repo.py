"""database/users_repo.py — пользователи и баланс кредитов доверия."""
from database.db import get_connection


def get_or_create_user(telegram_id: int, username: str | None, full_name: str | None):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE telegram_id = %s", (telegram_id,)
        ).fetchone()
        if row:
            # username/full_name могли измениться с прошлого визита — обновляем
            # и возвращаем свежую запись.
            conn.execute(
                "UPDATE users SET username = %s, full_name = %s WHERE telegram_id = %s",
                (username, full_name, telegram_id),
            )
            return conn.execute(
                "SELECT * FROM users WHERE telegram_id = %s", (telegram_id,)
            ).fetchone()
        conn.execute(
            "INSERT INTO users (telegram_id, username, full_name) VALUES (%s, %s, %s)",
            (telegram_id, username, full_name),
        )
        return conn.execute(
            "SELECT * FROM users WHERE telegram_id = %s", (telegram_id,)
        ).fetchone()


def get_user(telegram_id: int):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE telegram_id = %s", (telegram_id,)
        ).fetchone()


def get_credits(telegram_id: int) -> int:
    user = get_user(telegram_id)
    return user["credits"] if user else 0


def add_credits(telegram_id: int, amount: int) -> int:
    """Прибавляет amount к балансу (может быть 0). Возвращает новый баланс."""
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE users SET credits = credits + %s WHERE telegram_id = %s RETURNING credits",
            (amount, telegram_id),
        )
        return cur.fetchone()["credits"]


def set_credits(telegram_id: int, value: int) -> int:
    """Жёстко выставляет баланс кредитов (не прибавляет, а заменяет). Только
    для служебной функции 'изменить свои кредиты' в админ-панели
    (handlers/admin_panel.py) — быстрый способ для админа проверить, как
    выглядят карточка уровня и пороги доступа объектов при разных
    значениях, без ожидания реальных инсайдов. Upsert на случай, если у
    админа ещё нет записи в users (не должно случаться на практике — она
    создаётся при /start, — но так безопаснее)."""
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO users (telegram_id, credits) VALUES (%s, %s)
               ON CONFLICT (telegram_id) DO UPDATE SET credits = EXCLUDED.credits
               RETURNING credits""",
            (telegram_id, value),
        )
        return cur.fetchone()["credits"]


def get_all_telegram_ids() -> list[int]:
    """Все, у кого есть профиль (хоть раз писали боту) — источник для рассылок,
    например праздничных поздравлений (см. utils/holidays.py)."""
    with get_connection() as conn:
        rows = conn.execute("SELECT telegram_id FROM users").fetchall()
        return [row["telegram_id"] for row in rows]
