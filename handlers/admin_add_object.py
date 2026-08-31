"""
handlers/admin_add_object.py
--------------------------------
Сценарий "Добавить объект" (только админы), пошагово:
название → фото объекта → фото залаза → история → состояние → слухи →
координаты → порог доступа в кредитах → уровень опасности (обязательно,
одна из 5 кнопок) → подтверждение.

Каждый шаг ловит и неожиданный тип сообщения (см. *_wrong_type хендлеры
ниже) — без них бот молча игнорировал бы, например, фото вместо текста
истории объекта (найдено при отладке к 0.4, см. CHANGELOG).
"""
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
from database import objects_repo
from keyboards.admin_menu import (
    add_object_confirm_kb,
    add_object_photos_done_kb,
    admin_menu_kb,
    danger_level_pick_kb,
)
from states.object_states import AddObjectForm
from utils.access_control import is_admin
from utils.danger_levels import danger_line
from utils.formatting import esc, rich_text_or_none
from utils.validators import is_valid_coordinates, normalize_coordinates

router = Router(name="admin_add_object")


@router.callback_query(F.data == "admin:add_object")
async def start_add_object(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Только для модераторов.", show_alert=True)
        return
    await state.set_state(AddObjectForm.waiting_title)
    await callback.answer()
    await callback.message.answer("🆕 <b>Новый объект в архив</b>\n\nНазвание объекта:")


@router.message(AddObjectForm.waiting_title, F.text)
async def set_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=message.text.strip(), object_photos=[])
    await state.set_state(AddObjectForm.waiting_object_photos)
    await message.answer(
        "📸 <b>Шаг 1/3 — фото объекта</b>\n"
        "Пришлите одно или несколько фото объекта по очереди. "
        "Когда закончите — нажмите «Готово» (можно нажать сразу, если фото пока нет).",
        reply_markup=add_object_photos_done_kb("object"),
    )


@router.message(AddObjectForm.waiting_title)
async def title_wrong_type(message: Message) -> None:
    """Найдено при отладке к 0.4 (см. CHANGELOG): без этого хендлера
    непонятная админу тишина в ответ на что угодно, кроме текста (фото,
    голосовое и т.п.), на самом первом шаге сценария."""
    await message.answer("Ожидается текст — название объекта. Попробуйте ещё раз:")


@router.message(AddObjectForm.waiting_object_photos, F.photo)
async def add_object_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    photos = data.get("object_photos", [])
    photos.append(message.photo[-1].file_id)
    await state.update_data(object_photos=photos)
    await message.answer(f"✅ Фото объекта добавлено ({len(photos)}). Ещё, или «Готово».")


@router.message(AddObjectForm.waiting_object_photos)
async def object_photos_wrong_type(message: Message) -> None:
    await message.answer(
        "Ожидается фото объекта — пришлите его как обычное фото, или нажмите «Готово».",
        reply_markup=add_object_photos_done_kb("object"),
    )


@router.callback_query(AddObjectForm.waiting_object_photos, F.data == "objphoto:object:done")
async def object_photos_done(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(entry_photos=[])
    await state.set_state(AddObjectForm.waiting_entry_photos)
    await callback.answer()
    await callback.message.answer(
        "🚪 <b>Шаг 2/3 — фото залаза</b>\n"
        "Пришлите фото точки входа по очереди, затем «Готово» "
        "(можно пропустить, если залаза пока нет).",
        reply_markup=add_object_photos_done_kb("entry"),
    )


_RICH_TEXT_HINT = "Поддерживается форматирование Telegram (жирный, курсив, зачёркнутый, код и т.п.)."


@router.message(AddObjectForm.waiting_entry_photos, F.photo)
async def add_entry_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    photos = data.get("entry_photos", [])
    photos.append(message.photo[-1].file_id)
    await state.update_data(entry_photos=photos)
    await message.answer(f"✅ Фото залаза добавлено ({len(photos)}). Ещё, или «Готово».")


@router.message(AddObjectForm.waiting_entry_photos)
async def entry_photos_wrong_type(message: Message) -> None:
    await message.answer(
        "Ожидается фото залаза — пришлите его как обычное фото, или нажмите «Готово».",
        reply_markup=add_object_photos_done_kb("entry"),
    )


@router.callback_query(AddObjectForm.waiting_entry_photos, F.data == "objphoto:entry:done")
async def entry_photos_done(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddObjectForm.waiting_history)
    await callback.answer()
    await callback.message.answer(
        f"📜 История объекта. {_RICH_TEXT_HINT} Или «-», чтобы пропустить:"
    )


@router.message(AddObjectForm.waiting_history, F.text)
async def set_history(message: Message, state: FSMContext) -> None:
    await state.update_data(history=rich_text_or_none(message))
    await state.set_state(AddObjectForm.waiting_current_state)
    await message.answer(f"🏗 Нынешнее состояние объекта. {_RICH_TEXT_HINT}")


@router.message(AddObjectForm.waiting_history)
async def history_wrong_type(message: Message) -> None:
    await message.answer(f"Ожидается текст. {_RICH_TEXT_HINT} Или «-», чтобы пропустить:")


@router.message(AddObjectForm.waiting_current_state, F.text)
async def set_current_state(message: Message, state: FSMContext) -> None:
    await state.update_data(current_state=rich_text_or_none(message))
    await state.set_state(AddObjectForm.waiting_rumors)
    await message.answer(f"👂 Слухи вокруг объекта. {_RICH_TEXT_HINT} Или «-», чтобы пропустить:")


@router.message(AddObjectForm.waiting_current_state)
async def current_state_wrong_type(message: Message) -> None:
    await message.answer(f"Ожидается текст. {_RICH_TEXT_HINT}")


@router.message(AddObjectForm.waiting_rumors, F.text)
async def set_rumors(message: Message, state: FSMContext) -> None:
    await state.update_data(rumors=rich_text_or_none(message))
    await state.set_state(AddObjectForm.waiting_coordinates)
    await message.answer(
        "📍 <b>Шаг 3/3 — координаты</b>\n"
        "Скопируйте координаты из Google Maps в формате:\n"
        "<code>52°07'56.1\"N 26°01'02.5\"E</code>\n\n"
        "Или отправьте «-», если координаты неизвестны."
    )


@router.message(AddObjectForm.waiting_rumors)
async def rumors_wrong_type(message: Message) -> None:
    await message.answer(f"Ожидается текст. {_RICH_TEXT_HINT} Или «-», чтобы пропустить:")


@router.message(AddObjectForm.waiting_coordinates, F.text)
async def set_coordinates(message: Message, state: FSMContext) -> None:
    raw = message.text.strip()
    if raw == "-":
        coordinates = None
    elif is_valid_coordinates(raw):
        coordinates = normalize_coordinates(raw)
    else:
        await message.answer(
            "Не похоже на координаты из Google Maps. Нужен формат вида:\n"
            "<code>52°07'56.1\"N 26°01'02.5\"E</code>\n"
            "Или «-», чтобы пропустить. Попробуйте ещё раз:"
        )
        return

    await state.update_data(coordinates=coordinates)
    await state.set_state(AddObjectForm.waiting_min_credits)
    await message.answer(
        "🔒 Сколько кредитов доверия нужно для доступа к этому объекту?\n"
        f"Обязательное поле — целое число от {config.MIN_OBJECT_CREDITS} "
        f"до {config.MAX_OBJECT_CREDITS}. Пропустить нельзя."
    )


@router.message(AddObjectForm.waiting_coordinates)
async def coordinates_wrong_type(message: Message) -> None:
    await message.answer(
        "Нужны координаты текстом в формате:\n"
        "<code>52°07'56.1\"N 26°01'02.5\"E</code>\n"
        "Или «-», чтобы пропустить. Попробуйте ещё раз:"
    )


@router.message(AddObjectForm.waiting_min_credits, F.text)
async def set_min_credits(message: Message, state: FSMContext) -> None:
    raw = message.text.strip()
    if not raw.isdigit():
        await message.answer(
            "Нужно целое число (без «-» — цену пропустить нельзя). Попробуйте ещё раз:"
        )
        return

    value = int(raw)
    if not (config.MIN_OBJECT_CREDITS <= value <= config.MAX_OBJECT_CREDITS):
        await message.answer(
            f"Число должно быть от {config.MIN_OBJECT_CREDITS} до "
            f"{config.MAX_OBJECT_CREDITS}. Попробуйте ещё раз:"
        )
        return

    await state.update_data(min_credits=value)
    await state.set_state(AddObjectForm.waiting_danger_level)
    await message.answer(
        "⚠️ <b>Уровень опасности объекта</b>\n"
        "Обязательный пункт — выберите один из вариантов кнопкой ниже:",
        reply_markup=danger_level_pick_kb("adddanger"),
    )


@router.message(AddObjectForm.waiting_min_credits)
async def min_credits_wrong_type(message: Message) -> None:
    await message.answer(
        f"Нужно целое число текстом (от {config.MIN_OBJECT_CREDITS} до "
        f"{config.MAX_OBJECT_CREDITS}, без «-» — цену пропустить нельзя). Попробуйте ещё раз:"
    )


@router.callback_query(AddObjectForm.waiting_danger_level, F.data.regexp(r"^adddanger:(white|green|yellow|red|black)$"))
async def set_danger_level(callback: CallbackQuery, state: FSMContext) -> None:
    danger_level = callback.data.split(":")[1]
    await state.update_data(danger_level=danger_level)
    await state.set_state(AddObjectForm.confirm)
    await callback.answer()

    data = await state.get_data()
    summary = (
        f"<b>{esc(data['title'])}</b>\n\n"
        f"📸 Фото объекта: {len(data.get('object_photos', []))}\n"
        f"🚪 Фото залаза: {len(data.get('entry_photos', []))}\n"
        f"📜 История: {data.get('history') or '—'}\n"
        f"🏗 Состояние: {data.get('current_state') or '—'}\n"
        f"👂 Слухи: {data.get('rumors') or '—'}\n"
        f"📍 Координаты: {esc(data.get('coordinates')) or '—'}\n"
        f"🔒 Порог доступа: {data['min_credits']}\n"
        f"{danger_line(danger_level)}\n\n"
        "Сохранить объект в архив?"
    )
    await callback.message.answer(summary, reply_markup=add_object_confirm_kb())


@router.message(AddObjectForm.waiting_danger_level)
async def danger_level_wrong_type(message: Message) -> None:
    await message.answer(
        "Выберите уровень опасности одной из кнопок выше — свободный текст тут не принимается.",
        reply_markup=danger_level_pick_kb("adddanger"),
    )


@router.callback_query(AddObjectForm.confirm, F.data == "objconfirm:cancel")
async def cancel_add_object(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await callback.message.answer("Добавление объекта отменено.", reply_markup=admin_menu_kb())


@router.callback_query(AddObjectForm.confirm, F.data == "objconfirm:save")
async def save_object(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    object_id = objects_repo.create_object(
        title=data["title"],
        history=data.get("history"),
        current_state=data.get("current_state"),
        rumors=data.get("rumors"),
        coordinates=data.get("coordinates"),
        min_credits=data["min_credits"],
        danger_level=data.get("danger_level", config.DEFAULT_DANGER_LEVEL),
        created_by=callback.from_user.id,
    )
    for file_id in data.get("object_photos", []):
        objects_repo.add_object_photo(object_id, file_id, kind="object")
    for file_id in data.get("entry_photos", []):
        objects_repo.add_object_photo(object_id, file_id, kind="entry")

    await state.clear()
    await callback.answer()
    await callback.message.answer(
        f"✅ Объект «{esc(data['title'])}» добавлен в архив (id {object_id}).",
        reply_markup=admin_menu_kb(),
    )


@router.message(AddObjectForm.confirm)
async def confirm_wrong_type(message: Message) -> None:
    await message.answer("Нажмите «✅ Сохранить в архив» или «❌ Отмена» кнопкой выше.")
