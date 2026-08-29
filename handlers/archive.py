"""
handlers/archive.py
---------------------
Раздел "Архив": список объектов, карточка объекта (фото + текст),
отдельным блоком — фото залаза, если он есть.
"""
import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, InputMediaPhoto, Message

from database import objects_repo, users_repo
from keyboards.main_menu import BTN_ARCHIVE
from keyboards.objects_kb import objects_list_kb
from utils.access_control import has_object_access
from utils.formatting import CAPTION_LIMIT, format_object_card, plural_credits

router = Router(name="archive")
logger = logging.getLogger(__name__)


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
    try:
        object_id = int(callback.data.split(":", 1)[1])
    except ValueError:
        # Старая/повреждённая кнопка — не должно случаться в норме, но лучше
        # мягко ответить, чем уронить весь апдейт с необработанным исключением.
        await callback.answer("Некорректные данные кнопки.", show_alert=True)
        return

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
    обычным следующим сообщением.

    Фото может не отправиться (TelegramBadRequest "Wrong file identifier"),
    например если объект был добавлен через другого бота на этой же БД
    (см. config.BETA_BOT_TOKEN — file_id привязан к конкретному боту). В этом
    случае карточка не должна пропадать молча: ловим ошибку, логируем и всё
    равно доставляем текст, с пометкой, что фото не загрузилось."""
    if not photos:
        if caption:
            await message.answer(caption)
        return

    file_ids = [p["file_id"] for p in photos]
    fits = bool(caption) and len(caption) <= CAPTION_LIMIT

    try:
        if len(file_ids) == 1:
            if fits:
                await message.answer_photo(file_ids[0], caption=caption)
            else:
                await message.answer_photo(file_ids[0])
                if caption:
                    await message.answer(caption)
            return

        # caption передаётся сразу в конструктор: InputMediaPhoto — заморож-
        # енная (frozen) pydantic-модель в актуальных версиях aiogram,
        # присвоение `media[0].caption = ...` после создания кидает
        # ValidationError и роняет весь хендлер.
        media = [
            InputMediaPhoto(media=fid, caption=caption if fits and i == 0 else None)
            for i, fid in enumerate(file_ids)
        ]
        await message.answer_media_group(media)
        if caption and not fits:
            await message.answer(caption)
    except TelegramBadRequest as e:
        logger.warning("Не удалось отправить фото объекта %s: %s", file_ids, e)
        if caption:
            await message.answer(
                "⚠️ <i>Фото не загрузилось (техническая проблема с файлом) — "
                "обратитесь к админу.</i>\n\n" + caption
            )
