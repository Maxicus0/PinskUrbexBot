"""
database/insights_repo.py
----------------------------
CRUD для инсайдов (свободных сообщений пользователей), их медиафайлов и
модерации.

Начиная с релиза 0.4 инсайды в БД — это ТОЛЬКО очередь на модерацию, а не
постоянный архив. Строка живёт в таблице insights исключительно, пока имеет
status='pending': как только админ довёл его обработку до конца — оценил
(и, если нужно, дописал причину отказа и/или заметку об авторе) —
вызывается delete_insight(), и запись вместе со всеми её медиафайлами
(insight_media, ON DELETE CASCADE) удаляется из БД навсегда. Это сделано намеренно, чтобы БД не пухла от текстов/медиа
каждого когда-либо присланного инсайда (у некоторых бесплатных Postgres,
например на Render, есть жёсткий лимит объёма). Начисленные кредиты доверия
переживают удаление — они хранятся отдельно, в users.credits. Содержимое
самого инсайда после обработки остаётся только в переписке админа с ботом в
Telegram (сообщение, которое бот прислал во время оценки), см. README,
раздел «Безопасность и анонимность».
Поэтому колонки status/credits_awarded/rated_by/rated_at по факту больше не
используются (строка либо 'pending', либо её уже нет) — оставлены в схеме
только ради обратной совместимости со старыми базами, ничего в них не
записывается.
Поля type/related_object_* тоже оставлены в схеме ради обратной совместимости
и не участвуют в текущей логике. photo_file_id тоже legacy (одно фото) —
новые инсайды используют insight_media (фото и видео, до
config.MAX_INSIGHT_MEDIA штук).

С 0.4 user_id хранится зашифрованным (см. utils/crypto.py) — шифрование/
расшифровка происходит только здесь, вызывающий код (handlers/*) как и
раньше работает с обычным int telegram_id автора инсайда.
"""
from database.db import get_connection
from utils import crypto


def _decrypt_insight_row(row):
    if row is None:
        return None
    row["user_id"] = crypto.decrypt_id(row["user_id"])
    return row


def create_insight(user_id: int, text: str) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO insights (user_id, text) VALUES (%s, %s) RETURNING id",
            (crypto.encrypt_id(user_id), text),
        )
        return cur.fetchone()["id"]


def add_insight_media(insight_id: int, file_id: str, media_type: str = "photo") -> None:
    if media_type not in ("photo", "video"):
        raise ValueError(f"Некорректный media_type инсайда: {media_type!r}")
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO insight_media (insight_id, file_id, media_type) VALUES (%s, %s, %s)",
            (insight_id, file_id, media_type),
        )


def get_insight_media(insight_id: int):
    """Все медиафайлы инсайда по порядку добавления."""
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM insight_media WHERE insight_id = %s ORDER BY id",
            (insight_id,),
        ).fetchall()


def get_insight(insight_id: int):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM insights WHERE id = %s", (insight_id,)
        ).fetchone()
        return _decrypt_insight_row(row)


def get_pending_insights():
    """Порядок (created_at, id) должен совпадать с тем, как get_queue_position()
    считает номер очереди — иначе номера в списке ожидающих и в уведомлении/
    оценке (insight_submit.py, admin_rate_insight.py) могут разойтись."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM insights WHERE status = 'pending' ORDER BY created_at, id"
        ).fetchall()
        return [_decrypt_insight_row(row) for row in rows]


def count_pending_insights() -> int:
    """Сколько инсайдов сейчас ждут оценки — используется в коротком
    уведомлении админам при поступлении нового инсайда (без содержимого и
    кнопки оценки, см. handlers/insight_submit.py)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM insights WHERE status = 'pending'"
        ).fetchone()
        return row["n"]


def get_next_pending_insight():
    """Следующий инсайд на оценку — самый старый по времени подачи среди
    ожидающих, т.е. с наибольшим номером очереди (см. get_queue_position:
    нумерация отсчитывается от нового, #1, к старому, #N, поэтому «начать
    с конца очереди» означает начать со старейшего). Используется для
    последовательного разбора очереди строго по порядку поступления —
    от #N к #1 (см. handlers/admin_rate_insight.py,
    _advance_to_next_insight, и handlers/admin_panel.py, list_pending).
    None, если очередь пуста."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM insights WHERE status = 'pending' ORDER BY created_at, id LIMIT 1"
        ).fetchone()
        return _decrypt_insight_row(row)


def get_queue_position(insight_id: int) -> int:
    """Номер инсайда в очереди ожидающих, отсчитанный от старого к новому,
    но в обратную сторону: самый новый pending-инсайд всегда получает
    номер 1, а самый старый — номер, равный текущей длине очереди
    (например, при 3 ожидающих: новый = 1, средний = 2, самый старый = 3).
    Это НЕ id инсайда из БД: id — сквозной счётчик по всей истории и сам
    по себе показывает, сколько инсайдов всего когда-либо прислали.
    Номер пересчитывается на лету и меняется у уже существующих инсайдов
    по мере поступления новых — хранить его нельзя, только запрашивать
    заново. Вызывать, пока сам инсайд ещё pending — иначе позиция не
    определена (он уже вне очереди)."""
    with get_connection() as conn:
        row = conn.execute(
            """SELECT COUNT(*) AS n
               FROM insights
               WHERE status = 'pending'
                 AND (created_at, id) >= (
                     SELECT created_at, id FROM insights WHERE id = %s
                 )""",
            (insight_id,),
        ).fetchone()
        return row["n"]


def delete_insight(insight_id: int) -> None:
    """Удаляет инсайд и все его медиафайлы из БД — вызывается в самом конце
    обработки (см. module docstring выше): после оценки (и, если нужно,
    причины отказа/заметки об авторе). insight_media удаляется каскадно
    (ON DELETE CASCADE в schema.sql), отдельный запрос не нужен. Кредиты
    доверия нигде в этой таблице не сохраняются — начисление
    происходит отдельно, через users_repo.add_credits(), до вызова этой
    функции."""
    with get_connection() as conn:
        conn.execute("DELETE FROM insights WHERE id = %s", (insight_id,))
