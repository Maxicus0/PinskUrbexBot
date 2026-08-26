"""
scripts/smoke_test.py — самопроверка слоя БД и утилит без Telegram API.

Требует переменную окружения DATABASE_URL, указывающую на пустую/тестовую
PostgreSQL-базу (реальную базу бота лучше не использовать).

Запуск: python -m scripts.smoke_test
"""
import os

os.environ.setdefault("BOT_TOKEN", "smoketest:dummy")
os.environ.setdefault("ADMIN_IDS", "1")

if not os.environ.get("DATABASE_URL"):
    raise SystemExit(
        "Укажите DATABASE_URL (тестовая PostgreSQL-база) перед запуском smoke_test."
    )

from database import insights_repo, objects_repo, users_repo  # noqa: E402
from database.init_db import ensure_schema  # noqa: E402
from utils.access_control import has_object_access  # noqa: E402
from utils.levels import get_level_info  # noqa: E402
from utils.validators import coordinates_to_maps_url, is_valid_coordinates  # noqa: E402

USER_ID = 1001
ADMIN_ID = 1

COORDS = "52°07'56.1\"N 26°01'02.5\"E"


def run() -> None:
    ensure_schema()

    users_repo.get_or_create_user(USER_ID, "urbex_fan", "Иван")
    users_repo.get_or_create_user(ADMIN_ID, "moderator", "Модератор")
    print("[OK] пользователи созданы")

    assert is_valid_coordinates(COORDS)
    assert coordinates_to_maps_url(COORDS) is not None
    print("[OK] координаты в формате Google Maps распознаются и конвертируются")

    object_id = objects_repo.create_object(
        title="Заброшенный элеватор",
        history="Построен в 1960-х, закрыт в 2005",
        current_state="Крыша частично обвалилась",
        rumors="Говорят, там прячутся сталкеры",
        coordinates=COORDS,
        min_credits=3,
        created_by=ADMIN_ID,
    )
    objects_repo.add_object_photo(object_id, "FAKE_OBJECT_PHOTO_1", kind="object")
    objects_repo.add_object_photo(object_id, "FAKE_ENTRY_PHOTO_1", kind="entry")
    assert len(objects_repo.get_object_photos(object_id)) == 2
    print(f"[OK] объект #{object_id} создан с фото объекта и залаза")

    insight_id = insights_repo.create_insight(
        user_id=USER_ID,
        text="Обвалилась ещё одна секция крыши после грозы",
        photo_file_id=None,
    )
    assert insights_repo.get_insight(insight_id)["status"] == "pending"
    print(f"[OK] инсайд #{insight_id} создан со статусом pending")

    insights_repo.set_insight_rated(insight_id, 5, rated_by=ADMIN_ID)
    new_balance = users_repo.add_credits(USER_ID, 5)
    rated = insights_repo.get_insight(insight_id)
    assert rated["status"] == "approved" and rated["credits_awarded"] == 5
    print(f"[OK] инсайд оценён на 5, баланс пользователя = {new_balance}")

    obj = objects_repo.get_object(object_id)
    assert has_object_access(new_balance, obj["min_credits"])
    assert not has_object_access(new_balance, 10)
    print("[OK] проверка доступа по порогу кредитов работает корректно")

    level = get_level_info(new_balance)
    level_up = get_level_info(new_balance + 5)
    assert level.index == 0 and level_up.index == 1
    print(f"[OK] система уровней: {new_balance} кредитов = {level.name}, 10 кредитов = {level_up.name}")

    objects_repo.update_object_field(object_id, "title", "Элеватор (обновлено)")
    objects_repo.update_object_field(object_id, "min_credits", 7)
    updated = objects_repo.get_object(object_id)
    assert updated["title"] == "Элеватор (обновлено)" and updated["min_credits"] == 7
    print("[OK] update_object_field() меняет поля объекта")

    removed = objects_repo.clear_object_photos(object_id, kind="entry")
    assert removed == 1
    assert objects_repo.count_object_photos(object_id) == {"object": 1, "entry": 0}
    print("[OK] clear_object_photos()/count_object_photos() работают по kind")

    objects_repo.delete_object(object_id)
    assert objects_repo.get_object(object_id) is None
    print("[OK] delete_object() удаляет объект вместе с его фото (ON DELETE CASCADE)")

    print("\nВсё в порядке — слой базы данных и утилиты работают корректно.")


if __name__ == "__main__":
    run()
