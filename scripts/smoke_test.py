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
from utils.formatting import format_object_card, format_object_teaser  # noqa: E402
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
        danger_level="yellow",
        created_by=ADMIN_ID,
    )
    objects_repo.add_object_photo(object_id, "FAKE_OBJECT_PHOTO_1", kind="object")
    objects_repo.add_object_photo(object_id, "FAKE_ENTRY_PHOTO_1", kind="entry")
    assert len(objects_repo.get_object_photos(object_id)) == 2
    assert objects_repo.get_object(object_id)["danger_level"] == "yellow"
    print(f"[OK] объект #{object_id} создан с фото объекта и залаза, уровень опасности = yellow")

    objects_repo.update_object_field(object_id, "danger_level", "red")
    assert objects_repo.get_object(object_id)["danger_level"] == "red"
    print("[OK] уровень опасности объекта можно переназначить одним нажатием (update_object_field)")

    insight_id = insights_repo.create_insight(
        user_id=USER_ID,
        text="Обвалилась ещё одна секция крыши после грозы",
    )
    assert insights_repo.get_insight(insight_id)["status"] == "pending"
    print(f"[OK] инсайд #{insight_id} создан со статусом pending")

    insights_repo.add_insight_media(insight_id, "FAKE_INSIGHT_PHOTO_1", media_type="photo")
    insights_repo.add_insight_media(insight_id, "FAKE_INSIGHT_VIDEO_1", media_type="video")
    insight_media = insights_repo.get_insight_media(insight_id)
    assert len(insight_media) == 2
    assert {m["media_type"] for m in insight_media} == {"photo", "video"}
    print(f"[OK] к инсайду #{insight_id} прикреплены фото и видео (insight_media)")

    # Второй pending-инсайд — проверяем, что позиция в очереди считается по
    # порядку подачи, а не совпадает с id из БД (id2 = insight_id + 1, но
    # это по-прежнему второй, а не N-й в истории элемент в очереди).
    # Нумерация идёт от нового к старому: самый новый всегда #1, самый
    # старый — #N (при 2 ожидающих: insight_id, поданный первым, — #2,
    # а insight_id_2, поданный вторым и потому более новый, — #1).
    insight_id_2 = insights_repo.create_insight(user_id=USER_ID, text="Второй инсайд для теста очереди")
    assert insights_repo.get_queue_position(insight_id) == 2
    assert insights_repo.get_queue_position(insight_id_2) == 1
    print("[OK] get_queue_position() нумерует инсайды от нового (#1) к старому (#N), а не по id из БД")

    # get_next_pending_insight() — тот, с кем начинают оценку по кнопке
    # «Ожидающие инсайды»: самый старый, т.е. с наибольшим номером очереди.
    assert insights_repo.count_pending_insights() == 2
    assert insights_repo.get_next_pending_insight()["id"] == insight_id
    print("[OK] get_next_pending_insight() отдаёт самый старый инсайд (наибольший номер) первым")

    insights_repo.set_insight_rated(insight_id, 5, rated_by=ADMIN_ID)
    new_balance = users_repo.add_credits(USER_ID, 5)
    rated = insights_repo.get_insight(insight_id)
    assert rated["status"] == "approved" and rated["credits_awarded"] == 5
    print(f"[OK] инсайд оценён на 5, баланс пользователя = {new_balance}")

    # После оценки первого (старого) инсайда в очереди остаётся только
    # insight_id_2 — очередь всегда пересчитывается заново, а не запоминает
    # старые номера, поэтому единственный оставшийся инсайд — снова #1 и
    # именно он теперь следующий на очереди.
    assert insights_repo.get_queue_position(insight_id_2) == 1
    assert insights_repo.count_pending_insights() == 1
    assert insights_repo.get_next_pending_insight()["id"] == insight_id_2
    print("[OK] после оценки старого инсайда очередь пересчитывается")

    insights_repo.set_insight_rated(insight_id_2, 0, rated_by=ADMIN_ID)

    admin_new_balance = users_repo.set_credits(ADMIN_ID, 250)
    assert admin_new_balance == 250
    assert users_repo.get_credits(ADMIN_ID) == 250
    print("[OK] users_repo.set_credits() выставляет баланс админа для тестов")

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

    card_text = format_object_card(objects_repo.get_object(object_id))
    assert "🔴" in card_text and "Огромный шанс запала" in card_text
    teaser_unlocked = format_object_teaser(objects_repo.get_object(object_id), user_credits=999)
    assert teaser_unlocked.startswith("🔴")
    print("[OK] уровень опасности виден и в карточке, и в списке архива")

    objects_repo.delete_object(object_id)
    assert objects_repo.get_object(object_id) is None
    print("[OK] delete_object() удаляет объект вместе с его фото (ON DELETE CASCADE)")

    print("\nВсё в порядке — слой базы данных и утилиты работают корректно.")


if __name__ == "__main__":
    run()
