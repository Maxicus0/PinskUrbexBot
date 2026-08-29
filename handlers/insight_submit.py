"""
handlers/insight_submit.py
-----------------------------
Сценарий "Отправить инсайд": пользователь одним свободным сообщением
описывает новый объект/залаз/координаты/новость — без категорий, всё
уходит на одобрение админам. Поддерживает до config.MAX_INSIGHT_MEDIA
фото и/или видео (лимит нигде не анонсируется заранее — пользователь
узнаёт о нём, только если реально попробует прикрепить больше).

Безопасность и анонимность (см. README, раздел "Безопасность и
анонимность"): бот никогда не скачивает присланные файлы к себе — хранится
только telegram file_id (ссылка на файл на серверах Telegram), сами байты
бот не трогает. Принимаются только фото/видео, отправленные как обычное
медиа (не как файл/документ) — именно в таком виде Telegram сам сжимает и
переупаковывает файл при загрузке, стирая из него служебные метаданные
(в т.ч. GPS-координаты съёмки и модель устройства). Документы отправляют
исходные байты без этой обработки, поэтому такие вложения отклоняются
явным сообщением (см. _reject_document) — это защищает анонимность автора
инсайда.
"""
from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
from database import insights_repo
from keyboards.insight_kb import insight_confirm_kb, insight_media_kb, insight_start_kb
from keyboards.main_menu import BTN_SUBMIT_INSIGHT, main_menu_kb
from states.insight_states import InsightForm
from utils.access_control import is_admin
from utils.bot_delivery import send_message_to_user
from utils.formatting import esc

router = Router(name="insight_submit")

INSIGHT_PROMPT_TEXT = (
    "📤 <b>Отправка инсайда</b>\n\n"
    "Сюда принимается любая актуальная информация. "
    "Награда рассчитывается гибко в зависимости от ценности данных:\n\n"
    "• 💎 <b>Безоговорочные 10 кредитов доверия:</b> детальная история приема на объекте с пруфами, "
    "абсолютно новый эксклюзивный объект или свежий залаз;\n"
    "• 🔄 <b>Обновления архива:</b> новости по состоянию точек (заварили дверь, поставили камеру);\n"
    "• 📍 <b>Фактура:</b> точные координаты, ориентиры, схемы прохода, исторические документы. "
    "При отправке нового объекта вы можете сами написать, сколько кредитов доверия он, по вашему мнению, стоит, чтобы избежать несправедливости.\n\n"
    "Пишите всё, что знаете, в одном сообщении. Очень сильно награждаются инсайды с фото- или видео-пруфами. "
    "Это полностью анонимно, и бот не собирает никакой информации о вас, если вы сами не отправите её.\n\n"
    "Если вы считаете, что инсайд слишком плох или подобное, но он не содержит спама, то не бойтесь: "
    "бот <b>физически не может отнять токены</b> за плохой отчет. Он либо начислит от 1 до 10, либо отзовет с оценкой 0."
)

_TOO_MANY_MEDIA_TEXT = (
    f"❗️ Слишком много медиафайлов. Максимум {config.MAX_INSIGHT_MEDIA} на один инсайд. "
    "Нажмите «Готово», чтобы продолжить с уже прикреплённым."
)

_DOCUMENT_REJECTED_TEXT = (
    "⚠️ Файлы (документы) не принимаются — пришлите фото или видео обычным способом, "
    "как медиа, а не файлом. Так с него автоматически стираются технические данные "
    "(например, координаты съёмки), и вы остаётесь анонимны."
)


def _media_from_message(message: Message) -> tuple[str, str] | None:
    """(media_type, file_id) из сообщения с фото или видео, иначе None."""
    if message.photo:
        return "photo", message.photo[-1].file_id
    if message.video:
        return "video", message.video.file_id
    return None


async def _prompt_more_media(message: Message, count: int) -> None:
    await message.answer(
        f"✅ Добавлено ({count}/{config.MAX_INSIGHT_MEDIA}). Пришлите ещё фото/видео или нажмите «Готово».",
        reply_markup=insight_media_kb(),
    )


@router.message(F.text == BTN_SUBMIT_INSIGHT, StateFilter(None))
async def start_insight(message: Message, state: FSMContext) -> None:
    await state.set_state(InsightForm.waiting_content)
    await state.update_data(media=[])
    await message.answer(INSIGHT_PROMPT_TEXT, reply_markup=insight_start_kb())


@router.message(InsightForm.waiting_content, F.document)
@router.message(InsightForm.waiting_media, F.document)
async def content_document_rejected(message: Message) -> None:
    await message.answer(_DOCUMENT_REJECTED_TEXT)


@router.message(InsightForm.waiting_content, F.photo | F.video)
async def content_with_media(message: Message, state: FSMContext) -> None:
    media_type, file_id = _media_from_message(message)
    await state.update_data(media=[(media_type, file_id)])
    caption = message.caption.strip() if message.caption else None

    if caption:
        await state.update_data(text=caption)
        await state.set_state(InsightForm.waiting_media)
        await _prompt_more_media(message, 1)
        return

    await state.set_state(InsightForm.waiting_text_after_media)
    await message.answer("Добавьте текстовое описание к этому медиа:", reply_markup=insight_start_kb())


@router.message(InsightForm.waiting_text_after_media, F.text)
async def text_after_media(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text:
        await message.answer("Опишите хотя бы коротко, о чём инсайд:", reply_markup=insight_start_kb())
        return
    await state.update_data(text=text)
    data = await state.get_data()
    await state.set_state(InsightForm.waiting_media)
    await _prompt_more_media(message, len(data.get("media", [])))


@router.message(InsightForm.waiting_content, F.text)
async def content_text_only(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text:
        await message.answer("Опишите хотя бы коротко, о чём инсайд:", reply_markup=insight_start_kb())
        return
    await state.update_data(text=text, media=[])
    await state.set_state(InsightForm.waiting_media)
    await message.answer(
        "Приложите фото или видео (по желанию, можно несколько) или нажмите «Готово», "
        "если медиа не будет.",
        reply_markup=insight_media_kb(),
    )


@router.message(InsightForm.waiting_media, F.photo | F.video)
async def add_more_media(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    media = data.get("media", [])

    if len(media) >= config.MAX_INSIGHT_MEDIA:
        await message.answer(_TOO_MANY_MEDIA_TEXT, reply_markup=insight_media_kb())
        return

    media_type, file_id = _media_from_message(message)
    media.append((media_type, file_id))
    await state.update_data(media=media)
    await _prompt_more_media(message, len(media))


@router.callback_query(InsightForm.waiting_media, F.data == "insight:media_done")
async def media_done(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await _show_confirmation(callback.message, state)


async def _show_confirmation(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(InsightForm.confirm)

    media = data.get("media", [])
    if media:
        photos = sum(1 for media_type, _ in media if media_type == "photo")
        videos = sum(1 for media_type, _ in media if media_type == "video")
        parts = []
        if photos:
            parts.append(f"{photos} фото")
        if videos:
            parts.append(f"{videos} видео")
        media_summary = " + ".join(parts)
    else:
        media_summary = "нет"

    summary = (
        "👀 <b>Проверьте перед отправкой</b>\n\n"
        f"{esc(data.get('text'))}\n\n"
        f"Медиа: {media_summary}\n\n"
        "Отправить на проверку модераторам?"
    )
    await message.answer(summary, reply_markup=insight_confirm_kb())


@router.callback_query(InsightForm.confirm, F.data == "insight:cancel")
async def cancel_insight(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    admin = is_admin(callback.from_user.id)
    await callback.message.answer("Инсайд не отправлен.", reply_markup=main_menu_kb(is_admin=admin))


@router.callback_query(InsightForm.confirm, F.data == "insight:confirm")
async def confirm_insight(callback: CallbackQuery, state: FSMContext, bots: list[Bot]) -> None:
    data = await state.get_data()
    media: list[tuple[str, str]] = data.get("media", [])

    insight_id = insights_repo.create_insight(
        user_id=callback.from_user.id,
        text=data.get("text") or "(без текста)",
    )
    for media_type, file_id in media:
        insights_repo.add_insight_media(insight_id, file_id, media_type)

    await state.clear()
    await callback.answer()

    admin = is_admin(callback.from_user.id)
    await callback.message.answer(
        "✅ Инсайд отправлен на проверку. Как только модератор его оценит, "
        "вам придёт уведомление о начисленных кредитах доверия.",
        reply_markup=main_menu_kb(is_admin=admin),
    )

    # Админам НЕ показывается содержимое инсайда и НЕ предлагается кнопка
    # оценки прямо тут — только счётчик очереди. Чтобы начать оценивать,
    # админ жмёт «📋 Ожидающие инсайды» в админ-панели: оттуда его сразу
    # ведёт к самому старому инсайду, а не к списку со всеми сразу (см.
    # handlers/admin_panel.py, list_pending).
    total = insights_repo.count_pending_insights()
    notification_text = f"🔔 Новый инсайд. Всего в очереди на оценку: {total}."
    for admin_id in config.ADMIN_IDS:
        await send_message_to_user(bots, admin_id, notification_text)

