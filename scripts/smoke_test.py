"""
scripts/smoke_test.py — самопроверка слоя БД и утилит без Telegram API.

Требует переменную окружения DATABASE_URL (PostgreSQL) — и только её.
APP_SECRET_KEY указывать не нужно: если его нет в окружении, тест сам
сгенерирует случайный на время своего запуска. Реальным зашифрованным
данным бота этот ключ не нужен — utils/crypto.py требует его только чтобы
вообще согласиться загрузиться (см. его module docstring), а весь сценарий
теста выполняется в одной транзакции БД, которая в конце ВСЕГДА
откатывается (database.db.test_transaction) — ничего из того, что тест
записал (в том числе своим одноразовым ключом), в базе не остаётся.

Благодаря той же транзакции DATABASE_URL можно спокойно указывать ту же
базу, на которой уже крутится боевой и/или бета-бот (см. README, «Бета-бот
для локального теста») — пока тест выполняется, они его правок не видят
(PostgreSQL не показывает незакоммиченное чужим соединениям), а после
отката от них не остаётся и следа. Дополнительная страховка на случай, если
эту транзакционность в будущем случайно сломают рефакторингом — тестовые
USER_ID/ADMIN_ID ниже нарочно выбраны далеко за пределами диапазона
настоящих telegram_id, чтобы даже без отката не задеть строку реального
человека.

Запуск: python -m scripts.smoke_test
"""
import base64
import os
import secrets

os.environ.setdefault("BOT_TOKEN", "smoketest:dummy")
os.environ.setdefault("ADMIN_IDS", "9000000000002")
os.environ.setdefault(
    "APP_SECRET_KEY", base64.b64encode(secrets.token_bytes(32)).decode("ascii")
)

if not os.environ.get("DATABASE_URL"):
    raise SystemExit(
        "Укажите DATABASE_URL (PostgreSQL) перед запуском smoke_test — можно "
        "смело указывать даже ту базу, на которой уже работает боевой/бета-бот: "
        "тест выполняется в одной транзакции и в конце всегда откатывается, "
        "ничего в базе не меняя."
    )

from database import insights_repo, objects_repo, users_repo  # noqa: E402
from database.db import test_transaction  # noqa: E402
from database.init_db import ensure_schema  # noqa: E402
from utils.access_control import has_object_access  # noqa: E402
from utils.formatting import format_object_card, format_object_teaser  # noqa: E402
from utils.holidays import HOLIDAYS, format_bonus_line  # noqa: E402
from utils.levels import get_level_info  # noqa: E402
from utils.validators import coordinates_to_maps_url, is_valid_coordinates  # noqa: E402

# Далеко за пределами реального диапазона telegram_id (у Telegram он по
# состоянию на 2026 год не доходит до 10^10) — см. пояснение в module
# docstring выше.
USER_ID = 9_000_000_000_001
ADMIN_ID = 9_000_000_000_002

COORDS = "52°07'56.1\"N 26°01'02.5\"E"


def run() -> None:
    with test_transaction():
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

        # С 0.4 инсайды в БД временные (см. module docstring database/
        # insights_repo.py): "оценка" — это начисление кредитов напрямую в
        # users.credits + delete_insight(), а не запись статуса в саму строку
        # insights. Проверяем именно это: кредиты долетают, а от инсайда и его
        # медиа в БД не остаётся ни следа.
        new_balance = users_repo.add_credits(USER_ID, 5)
        insights_repo.delete_insight(insight_id)
        assert insights_repo.get_insight(insight_id) is None
        assert insights_repo.get_insight_media(insight_id) == []
        print(f"[OK] после оценки на 5 инсайд и его медиа удалены из БД (транзитом), баланс пользователя = {new_balance}")

        # После удаления первого (старого) инсайда в очереди остаётся только
        # insight_id_2 — очередь всегда пересчитывается заново, а не запоминает
        # старые номера, поэтому единственный оставшийся инсайд — снова #1 и
        # именно он теперь следующий на очереди.
        assert insights_repo.get_queue_position(insight_id_2) == 1
        assert insights_repo.count_pending_insights() == 1
        assert insights_repo.get_next_pending_insight()["id"] == insight_id_2
        print("[OK] после удаления старого инсайда очередь пересчитывается")

        # 0 кредитов (отказ) с 0.4 тоже завершается удалением — только после
        # того, как обязательная причина отказа отправлена автору (сама причина
        # никуда в БД не пишется, только уходит в чат, см. handlers/
        # admin_rate_insight.py, apply_reject_reason). Здесь просто проверяем
        # финальный эффект на БД: полное удаление, кредиты не начисляются.
        insights_repo.delete_insight(insight_id_2)
        assert insights_repo.get_insight(insight_id_2) is None
        assert insights_repo.count_pending_insights() == 0
        print("[OK] отклонённый (0 кредитов) инсайд тоже полностью удаляется из БД")

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
        assert teaser_unlocked.startswith("🗂") and "🔴" not in teaser_unlocked and teaser_unlocked.endswith("📍")
        teaser_locked = format_object_teaser(objects_repo.get_object(object_id), user_credits=0)
        assert teaser_locked.startswith("🔒") and "🗂" not in teaser_locked
        print("[OK] уровень опасности виден в карточке, но не в тизере списка архива (🗂 + название + пин)")

        # /settings — личный режим отображения архива (config.ARCHIVE_DISPLAY_MODES).
        assert users_repo.get_archive_display_mode(USER_ID) == "standard"
        assert users_repo.set_archive_display_mode(USER_ID, "danger_color") == "danger_color"
        assert users_repo.get_archive_display_mode(USER_ID) == "danger_color"
        teaser_danger_color = format_object_teaser(
            objects_repo.get_object(object_id), user_credits=999, display_mode="danger_color"
        )
        assert teaser_danger_color.startswith("🔴") and "🗂" not in teaser_danger_color
        users_repo.set_archive_display_mode(USER_ID, "standard")  # возвращаем дефолт для чистоты теста
        print("[OK] /settings: режим 'danger_color' подставляет эмодзи опасности вместо 🗂 в тизере")

        objects_repo.delete_object(object_id)
        assert objects_repo.get_object(object_id) is None
        print("[OK] delete_object() удаляет объект вместе с его фото (ON DELETE CASCADE)")

        # Регресс-проверка на найденный при отладке к 0.4 мёртвый код: раньше
        # у каждого праздника в HOLIDAYS хранилось неиспользуемое поле
        # "bonus_word" (реальное склонение вычисляет _bonus_word() через
        # plural_credits()) — убеждаемся, что поля больше нет и что подстановка
        # {bonus}/{bonus_word} в текстах всё равно работает без ошибок.
        for holiday in HOLIDAYS:
            assert "bonus_word" not in holiday
            line = format_bonus_line(holiday)
            assert "{bonus" not in line
        print(f"[OK] все {len(HOLIDAYS)} праздников без мёртвого поля bonus_word, склонение считается на лету")

        print("\nВсё в порядке — слой базы данных и утилиты работают корректно.")


if __name__ == "__main__":
    run()
