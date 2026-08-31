"""database/users_repo.py — пользователи и баланс кредитов доверия.

С 0.4 telegram_id/username/full_name хранятся в БД зашифрованными (см.
utils/crypto.py и schema.sql) — этот модуль единственное место, где это
шифрование/расшифровка происходит. Вызывающий код (handlers/*) как раньше
работает с обычными Python int/str telegram_id/username/full_name и не
подозревает о шифровании — все функции здесь принимают и возвращают только
расшифрованные значения.
"""
import config
from database.db import get_connection
from utils import crypto


def _decrypt_user_row(row):
    if row is None:
        return None
    row["telegram_id"] = crypto.decrypt_id(row["telegram_id"])
    row["username"] = crypto.decrypt_text(row["username"])
    row["full_name"] = crypto.decrypt_text(row["full_name"])
    return row


def get_or_create_user(telegram_id: int, username: str | None, full_name: str | None):
    enc_id = crypto.encrypt_id(telegram_id)
    enc_username = crypto.encrypt_text(username)
    enc_full_name = crypto.encrypt_text(full_name)
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE telegram_id = %s", (enc_id,)
        ).fetchone()
        if row:
            # username/full_name могли измениться с прошлого визита — обновляем
            # и возвращаем свежую запись.
            conn.execute(
                "UPDATE users SET username = %s, full_name = %s WHERE telegram_id = %s",
                (enc_username, enc_full_name, enc_id),
            )
            row = conn.execute(
                "SELECT * FROM users WHERE telegram_id = %s", (enc_id,)
            ).fetchone()
            return _decrypt_user_row(row)
        conn.execute(
            "INSERT INTO users (telegram_id, username, full_name) VALUES (%s, %s, %s)",
            (enc_id, enc_username, enc_full_name),
        )
        row = conn.execute(
            "SELECT * FROM users WHERE telegram_id = %s", (enc_id,)
        ).fetchone()
        return _decrypt_user_row(row)


def get_user(telegram_id: int):
    enc_id = crypto.encrypt_id(telegram_id)
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE telegram_id = %s", (enc_id,)
        ).fetchone()
        return _decrypt_user_row(row)


def get_credits(telegram_id: int) -> int:
    user = get_user(telegram_id)
    return user["credits"] if user else 0


def add_credits(telegram_id: int, amount: int) -> int:
    """Прибавляет amount к балансу (может быть 0). Возвращает новый баланс."""
    enc_id = crypto.encrypt_id(telegram_id)
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE users SET credits = credits + %s WHERE telegram_id = %s RETURNING credits",
            (amount, enc_id),
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
    enc_id = crypto.encrypt_id(telegram_id)
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO users (telegram_id, credits) VALUES (%s, %s)
               ON CONFLICT (telegram_id) DO UPDATE SET credits = EXCLUDED.credits
               RETURNING credits""",
            (enc_id, value),
        )
        return cur.fetchone()["credits"]


def get_all_telegram_ids() -> list[int]:
    """Все, у кого есть профиль (хоть раз писали боту) — источник для рассылок,
    например праздничных поздравлений (см. utils/holidays.py)."""
    with get_connection() as conn:
        rows = conn.execute("SELECT telegram_id FROM users").fetchall()
        return [crypto.decrypt_id(row["telegram_id"]) for row in rows]


def get_archive_display_mode(telegram_id: int) -> str:
    """Личный режим отображения объектов в списке "🗂 Архив" (см. /settings,
    handlers/settings.py, config.ARCHIVE_DISPLAY_MODES). Если у пользователя
    ещё нет профиля (ни разу не писал боту) — стандартный режим по умолчанию,
    без обращения к БД."""
    user = get_user(telegram_id)
    return user["archive_display_mode"] if user else config.DEFAULT_ARCHIVE_DISPLAY_MODE


def set_archive_display_mode(telegram_id: int, mode: str) -> str:
    """Ставит режим отображения архива для пользователя (см. /settings).
    Upsert — на случай гонки с ещё не отправленным /start, хотя на практике
    кнопки /settings недостижимы до создания профиля."""
    enc_id = crypto.encrypt_id(telegram_id)
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO users (telegram_id, archive_display_mode) VALUES (%s, %s)
               ON CONFLICT (telegram_id) DO UPDATE SET archive_display_mode = EXCLUDED.archive_display_mode
               RETURNING archive_display_mode""",
            (enc_id, mode),
        )
        return cur.fetchone()["archive_display_mode"]
