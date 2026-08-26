"""
database/objects_repo.py
--------------------------
CRUD для объектов архива и их фотографий.

object_photos.kind: "object" — фото самого объекта, "entry" — фото залаза.
"""
from database.db import get_connection


def create_object(
    title,
    history,
    current_state,
    rumors,
    coordinates,
    min_credits,
    created_by,
) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO objects
               (title, history, current_state, rumors, coordinates, min_credits, created_by)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (title, history, current_state, rumors, coordinates, min_credits, created_by),
        )
        return cur.fetchone()["id"]


def add_object_photo(object_id: int, file_id: str, kind: str = "object", caption: str | None = None) -> None:
    if kind not in ("object", "entry"):
        raise ValueError(f"Некорректный kind фото объекта: {kind!r}")
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO object_photos (object_id, file_id, kind, caption) VALUES (%s, %s, %s, %s)",
            (object_id, file_id, kind, caption),
        )


def get_object(object_id: int):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM objects WHERE id = %s", (object_id,)
        ).fetchone()


def list_objects(status: str = "published"):
    """Объекты для раздела "Архив", отсортированные по возрастанию цены
    (min_credits), при равной цене — по алфавиту."""
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM objects WHERE status = %s "
            "ORDER BY min_credits ASC, LOWER(title) ASC",
            (status,),
        ).fetchall()


def get_object_photos(object_id: int, kind: str | None = None):
    """Все фото объекта по порядку добавления. kind=None — все фото."""
    with get_connection() as conn:
        if kind is None:
            return conn.execute(
                "SELECT * FROM object_photos WHERE object_id = %s ORDER BY id",
                (object_id,),
            ).fetchall()
        return conn.execute(
            "SELECT * FROM object_photos WHERE object_id = %s AND kind = %s ORDER BY id",
            (object_id, kind),
        ).fetchall()


def list_objects_all():
    """Все объекты (любой status) — для админ-панели управления объектами."""
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM objects ORDER BY LOWER(title) ASC"
        ).fetchall()


_EDITABLE_FIELDS = {"title", "history", "current_state", "rumors", "coordinates", "min_credits"}


def update_object_field(object_id: int, field: str, value) -> None:
    """Обновляет одно поле объекта. field сверяется с белым списком
    _EDITABLE_FIELDS, чтобы имя колонки никогда не собиралось из
    пользовательского ввода напрямую в SQL."""
    if field not in _EDITABLE_FIELDS:
        raise ValueError(f"Недопустимое поле для обновления объекта: {field!r}")
    with get_connection() as conn:
        conn.execute(
            f"UPDATE objects SET {field} = %s, updated_at = NOW() WHERE id = %s",
            (value, object_id),
        )


def delete_object(object_id: int) -> None:
    """Удаляет объект; его фото удаляются каскадно (ON DELETE CASCADE)."""
    with get_connection() as conn:
        conn.execute("DELETE FROM objects WHERE id = %s", (object_id,))


def clear_object_photos(object_id: int, kind: str) -> int:
    """Удаляет все фото объекта заданного вида, возвращает число удалённых строк."""
    if kind not in ("object", "entry"):
        raise ValueError(f"Некорректный kind фото объекта: {kind!r}")
    with get_connection() as conn:
        cur = conn.execute(
            "DELETE FROM object_photos WHERE object_id = %s AND kind = %s",
            (object_id, kind),
        )
        return cur.rowcount


def count_object_photos(object_id: int) -> dict:
    """{'object': N, 'entry': M} — количество фото каждого вида."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT kind, COUNT(*) AS n FROM object_photos WHERE object_id = %s GROUP BY kind",
            (object_id,),
        ).fetchall()
    counts = {"object": 0, "entry": 0}
    for row in rows:
        counts[row["kind"]] = row["n"]
    return counts
