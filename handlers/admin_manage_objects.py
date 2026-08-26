"""
handlers/admin_manage_objects.py
------------------------------------
Управление объектами архива (только админы): редактирование полей и
фото, удаление с двумя подтверждениями подряд.

Точка входа — кнопка "📂 Объекты архива" в админ-панели (admin:objects).

Схема callback_data:
  admin:objects                          — список всех объектов
  adminobj:<id>                          — карточка управления объектом
  adminobj:<id>:edit                     — меню выбора поля для редактирования
  adminobj:<id>:delete                   — первый шаг подтверждения удаления
  objedit:<id>:<field>                   — начать редактирование текстового поля
  objedit:<id>:object_photos|entry_photos — начать редактирование фото
  objeditphoto:<id>:<kind>:clear|done    — очистить/завершить редактирование фото
  objdel:<id>:confirm1                   — второй (финальный) шаг подтверждения
  objdel:<id>:confirm2                   — реальное удаление
"""
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
from database import objects_repo
from keyboards.admin_menu import (
    admin_object_manage_kb,
    admin_objects_list_kb,
    delete_object_confirm_kb,
    delete_object_final_confirm_kb,
    edit_object_fields_kb,
    edit_photos_kb,
)
from states.object_states import EditObjectForm
from utils.access_control import is_admin
from utils.formatting import esc, format_object_card
from utils.validators import is_valid_coordinates, normalize_coordinates

router = Router(name="admin_manage_objects")

_FIELD_LABELS = {
    "title": "Название",
    "history": "История",
    "current_state": "Нынешнее состояние",
    "rumors": "Слухи",
    "coordinates": "Координаты",
    "min_credits": "Порог доступа",
}
_PHOTO_KIND_LABELS = {"object": "объекта", "entry": "залаза"}
_TEXT_FIELDS_PATTERN = r"^objedit:\d+:(title|history|current_state|rumors|coordinates|min_credits)$"
_PHOTO_FIELDS_PATTERN = r"^objedit:\d+:(object_photos|entry_photos)$"
_PHOTO_CLEAR_PATTERN = r"^objeditphoto:\d+:(object|entry):clear$"
_PHOTO_DONE_PATTERN = r"^objeditphoto:\d+:(object|entry):done$"


def _manage_card_text(obj, photo_counts: dict) -> str:
    return (
        f"{format_object_card(obj)}\n\n"
        f"🔐 Порог доступа: {obj['min_credits']}\n"
        f"📸 Фото объекта: {photo_counts['object']} · 🚪 Фото залаза: {photo_counts['entry']}\n"
        f"🆔 id {obj['id']} · статус {obj['status']}"
    )


async def _show_manage_card(message: Message, object_id: int) -> None:
    obj = objects_repo.get_object(object_id)
    if not obj:
        await message.answer("Объект не найден — возможно, он уже удалён.")
        return
    counts = objects_repo.count_object_photos(object_id)
    await message.answer(_manage_card_text(obj, counts), reply_markup=admin_object_manage_kb(object_id))


def _field_prompt(field: str) -> str:
    if field == "title":
        return "Пришлите новое название."
    if field == "coordinates":
        return (
            "Пришлите новые координаты в формате Google Maps:\n"
            "<code>52°07'56.1\"N 26°01'02.5\"E</code>\n"
            "Или «-», чтобы очистить координаты."
        )
    if field == "min_credits":
        return (
            f"Пришлите новый порог доступа — целое число кредитов доверия "
            f"от {config.MIN_OBJECT_CREDITS} до {config.MAX_OBJECT_CREDITS}."
        )
    return "Пришлите новый текст. Отправьте «-», чтобы очистить поле."


# ---------- список и карточка объекта ----------

@router.callback_query(F.data == "admin:objects")
async def list_admin_objects(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Только для модераторов.", show_alert=True)
        return
    await state.clear()
    await callback.answer()

    objects = objects_repo.list_objects_all()
    if not objects:
        await callback.message.answer("Архив пока пуст — объекты ещё не добавлены.")
        return
    await callback.message.answer(
        "📂 <b>Объекты архива</b>\nВыберите объект, чтобы отредактировать или удалить его.",
        reply_markup=admin_objects_list_kb(objects),
    )


@router.callback_query(F.data.regexp(r"^adminobj:\d+$"))
async def open_manage_card(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Только для модераторов.", show_alert=True)
        return
    await state.clear()
    object_id = int(callback.data.split(":")[1])
    await callback.answer()
    await _show_manage_card(callback.message, object_id)


# ---------- редактирование: выбор поля ----------

@router.callback_query(F.data.regexp(r"^adminobj:\d+:edit$"))
async def open_edit_menu(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Только для модераторов.", show_alert=True)
        return
    object_id = int(callback.data.split(":")[1])
    obj = objects_repo.get_object(object_id)
    if not obj:
        await callback.answer("Объект не найден.", show_alert=True)
        return
    await state.clear()
    await callback.answer()
    await callback.message.answer(
        f"✏️ Что изменить у «{esc(obj['title'])}»?",
        reply_markup=edit_object_fields_kb(object_id),
    )


@router.callback_query(F.data.regexp(_TEXT_FIELDS_PATTERN))
async def start_edit_field(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Только для модераторов.", show_alert=True)
        return
    _, object_id_raw, field = callback.data.split(":")
    object_id = int(object_id_raw)
    obj = objects_repo.get_object(object_id)
    if not obj:
        await callback.answer("Объект не найден.", show_alert=True)
        return

    await state.set_state(EditObjectForm.waiting_value)
    await state.update_data(object_id=object_id, field=field)
    await callback.answer()

    current = obj[field]
    current_text = esc(current) if current not in (None, "") else "—"
    await callback.message.answer(
        f"Текущее значение ({_FIELD_LABELS[field]}): {current_text}\n\n{_field_prompt(field)}"
    )


@router.message(EditObjectForm.waiting_value, F.text)
async def apply_field_edit(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    object_id = data["object_id"]
    field = data["field"]
    raw = message.text.strip()

    if field == "title":
        if not raw or raw == "-":
            await message.answer("Название не может быть пустым. Пришлите новое название:")
            return
        value = raw

    elif field == "coordinates":
        if raw == "-":
            value = None
        elif is_valid_coordinates(raw):
            value = normalize_coordinates(raw)
        else:
            await message.answer(
                "Не похоже на координаты из Google Maps. Нужен формат вида:\n"
                "<code>52°07'56.1\"N 26°01'02.5\"E</code>\n"
                "Или «-», чтобы очистить. Попробуйте ещё раз:"
            )
            return

    elif field == "min_credits":
        if not raw.isdigit():
            await message.answer("Нужно целое число. Попробуйте ещё раз:")
            return
        value = int(raw)
        if not (config.MIN_OBJECT_CREDITS <= value <= config.MAX_OBJECT_CREDITS):
            await message.answer(
                f"Число должно быть от {config.MIN_OBJECT_CREDITS} до "
                f"{config.MAX_OBJECT_CREDITS}. Попробуйте ещё раз:"
            )
            return

    else:  # history / current_state / rumors — свободный текст, "-" очищает поле
        value = None if raw == "-" else raw

    objects_repo.update_object_field(object_id, field, value)
    await state.clear()

    await message.answer(
        f"✅ Поле «{_FIELD_LABELS[field]}» обновлено.",
        reply_markup=edit_object_fields_kb(object_id),
    )


# ---------- редактирование: фото ----------

@router.callback_query(F.data.regexp(_PHOTO_FIELDS_PATTERN))
async def start_edit_photos(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Только для модераторов.", show_alert=True)
        return
    _, object_id_raw, field = callback.data.split(":")
    object_id = int(object_id_raw)
    kind = "object" if field == "object_photos" else "entry"

    obj = objects_repo.get_object(object_id)
    if not obj:
        await callback.answer("Объект не найден.", show_alert=True)
        return

    counts = objects_repo.count_object_photos(object_id)
    await state.set_state(EditObjectForm.waiting_photos)
    await state.update_data(object_id=object_id, photo_kind=kind)
    await callback.answer()
    await callback.message.answer(
        f"📸 Сейчас фото {_PHOTO_KIND_LABELS[kind]}: {counts[kind]}.\n"
        "Пришлите новые фото по очереди — они добавятся к существующим. "
        "Если нужно заменить набор целиком — сперва нажмите «Очистить старые фото».",
        reply_markup=edit_photos_kb(object_id, kind),
    )


@router.message(EditObjectForm.waiting_photos, F.photo)
async def add_edit_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    object_id = data["object_id"]
    kind = data["photo_kind"]
    objects_repo.add_object_photo(object_id, message.photo[-1].file_id, kind=kind)
    counts = objects_repo.count_object_photos(object_id)
    await message.answer(
        f"✅ Фото добавлено ({counts[kind]} всего). Ещё, «Очистить старые фото» или «Готово».",
        reply_markup=edit_photos_kb(object_id, kind),
    )


@router.callback_query(EditObjectForm.waiting_photos, F.data.regexp(_PHOTO_CLEAR_PATTERN))
async def clear_edit_photos(callback: CallbackQuery, state: FSMContext) -> None:
    _, object_id_raw, kind, _action = callback.data.split(":")
    object_id = int(object_id_raw)
    removed = objects_repo.clear_object_photos(object_id, kind)
    await callback.answer(f"Удалено фото: {removed}.")
    await callback.message.answer(
        f"🗑 Старые фото {_PHOTO_KIND_LABELS[kind]} очищены ({removed}). "
        "Присылайте новые, затем «Готово».",
        reply_markup=edit_photos_kb(object_id, kind),
    )


@router.callback_query(EditObjectForm.waiting_photos, F.data.regexp(_PHOTO_DONE_PATTERN))
async def finish_edit_photos(callback: CallbackQuery, state: FSMContext) -> None:
    _, object_id_raw, _kind, _action = callback.data.split(":")
    object_id = int(object_id_raw)
    await state.clear()
    await callback.answer()
    obj = objects_repo.get_object(object_id)
    if not obj:
        await callback.answer("Объект не найден.", show_alert=True)
        return
    await callback.message.answer(
        f"✅ Фото «{esc(obj['title'])}» обновлены.",
        reply_markup=edit_object_fields_kb(object_id),
    )


# ---------- удаление с двумя подтверждениями ----------

@router.callback_query(F.data.regexp(r"^adminobj:\d+:delete$"))
async def ask_delete_confirm1(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Только для модераторов.", show_alert=True)
        return
    object_id = int(callback.data.split(":")[1])
    obj = objects_repo.get_object(object_id)
    if not obj:
        await callback.answer("Объект не найден.", show_alert=True)
        return
    await state.clear()
    await callback.answer()
    await callback.message.answer(
        f"⚠️ Удалить объект «{esc(obj['title'])}» из архива вместе со всеми фото?\n"
        "Это первое из двух подтверждений — объект пока не удалён.",
        reply_markup=delete_object_confirm_kb(object_id),
    )


@router.callback_query(F.data.regexp(r"^objdel:\d+:confirm1$"))
async def ask_delete_confirm2(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Только для модераторов.", show_alert=True)
        return
    object_id = int(callback.data.split(":")[1])
    obj = objects_repo.get_object(object_id)
    if not obj:
        await callback.answer("Объект не найден.", show_alert=True)
        return
    await callback.answer()
    await callback.message.answer(
        f"❗️ Точно удалить «{esc(obj['title'])}»? Это действие необратимо — "
        "объект и все его фото будут удалены навсегда.",
        reply_markup=delete_object_final_confirm_kb(object_id),
    )


@router.callback_query(F.data.regexp(r"^objdel:\d+:confirm2$"))
async def perform_delete(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Только для модераторов.", show_alert=True)
        return
    object_id = int(callback.data.split(":")[1])
    obj = objects_repo.get_object(object_id)
    if not obj:
        await callback.answer("Объект уже удалён.", show_alert=True)
        return

    title = obj["title"]
    objects_repo.delete_object(object_id)
    await callback.answer("Удалено.")
    await callback.message.answer(f"🗑 Объект «{esc(title)}» удалён из архива.")

    objects = objects_repo.list_objects_all()
    if objects:
        await callback.message.answer(
            "📂 Объекты архива:", reply_markup=admin_objects_list_kb(objects)
        )
