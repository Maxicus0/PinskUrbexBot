"""
handlers/archive.py
---------------------
Раздел "Архив": список объектов, карточка объекта (фото + текст),
отдельным блоком — фото залаза, если он есть.
"""
from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, InputMediaPhoto, Message

from database import objects_repo, users_repo
from keyboards.main_menu import BTN_ARCHIVE
from keyboards.objects_kb import objects_list_kb
from utils.access_control import has_object_access
from utils.formatting import CAPTION_LIMIT, format_object_card, plural_credits

router = Router(name="archive")


@router.message(F.text == BTN_ARCHIVE, StateFilter(None))
async def open_archive(message: Message) -> None:
    credits = users_repo.get_credits(message.from_user.id)
    objects = objects_repo.list_objects()
    if not objects:
        await message.answer("Архив пока пуст — объекты ещё не добавлены.")
        return

    await message.answer(
        "🗂 <b>Объекты архива</b>\n"
        "🔒 — объект скрыт, не хватает кредитов доверия (нужное количество — на кнопке), "
        "📍 — известны координаты.",
        reply_markup=objects_list_kb(objects, credits),
    )


@router.callback_query(F.data.startswith("obj:"))
async def open_object_card(callback: CallbackQuery) -> None:
    object_id = int(callback.data.split(":", 1)[1])
    obj = objects_repo.get_object(object_id)
    if not obj:
        await callback.answer("Объект не найден.", show_alert=True)
        return

    credits = users_repo.get_credits(callback.from_user.id)

    # Список объектов уже отфильтрован по порогу конкретного объекта, но
    # карточку теоретически можно открыть напрямую по старой callback-кнопке,
    # так что дублируем проверку здесь для консистентности.
    if not has_object_access(credits, obj["min_credits"]):
        await callback.answer(
            f"🔒 Нужно {obj['min_credits']} {plural_credits(obj['min_credits'])} доверия "
            f"(у вас {credits}).",
            show_alert=True,
        )
        return

    await callback.answer()

    card_text = format_object_card(obj)
    object_photos = objects_repo.get_object_photos(object_id, kind="object")
    entry_photos = objects_repo.get_object_photos(object_id, kind="entry")

    await _send_photo_block(callback.message, object_photos, card_text)

    if entry_photos:
        await _send_photo_block(
            callback.message, entry_photos, "🚪 <b>Как попасть (залаз)</b>"
        )


async def _send_photo_block(message: Message, photos, caption: str | None) -> None:
    """Отправляет серию фото с подписью. Если текст не влезает в лимит
    подписи Telegram (1024 символа), фото уходит без подписи, а текст —
    обычным следующим сообщением."""
    if not photos:
        if caption:
            await message.answer(caption)
        return

    file_ids = [p["file_id"] for p in photos]
    fits = bool(caption) and len(caption) <= CAPTION_LIMIT

    if len(file_ids) == 1:
        if fits:
            await message.answer_photo(file_ids[0], caption=caption)
        else:
            await message.answer_photo(file_ids[0])
            if caption:
                await message.answer(caption)
        return

    media = [InputMediaPhoto(media=fid) for fid in file_ids]
    if fits:
        media[0].caption = caption
        await message.answer_media_group(media)
    else:
        await message.answer_media_group(media)
        if caption:
            await message.answer(caption)
