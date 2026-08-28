"""
handlers/insight_submit.py
-----------------------------
Сценарий "Отправить инсайд": пользователь одним свободным сообщением
описывает новый объект/залаз/координаты/новость — без категорий, всё
уходит на одобрение админам. Поддерживает фото с подписью или отдельным
сообщением.
"""
from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
from database import insights_repo
from keyboards.insight_kb import (
    insight_confirm_kb,
    insight_skip_photo_kb,
    insight_start_kb,
    rate_insight_kb,
)
from keyboards.main_menu import BTN_SUBMIT_INSIGHT, main_menu_kb
from states.insight_states import InsightForm
from utils.access_control import is_admin
from utils.bot_delivery import send_message_to_user
from utils.formatting import CAPTION_LIMIT, esc, format_insight_notification

router = Router(name="insight_submit")

INSIGHT_PROMPT_TEXT = (
    "📤 <b>Отправка инсайда</b>\n\n"
    "Опишите одним сообщением всё, что знаете:\n"
    "• 🆕 новый объект для архива — что это и где;\n"
    "• 🚪 залаз — как попасть внутрь;\n"
    "• 📍 координаты;\n"
    "• 🔄 новость или обновление по уже известному объекту;\n"
    "• 💰 ваша оценка — сколько токенов, по-вашему, стоит объект.\n\n"
    "Заполнять всё не обязательно — пишите, что знаете. Фото объекта можно "
    "приложить сразу (отправьте его с этим текстом в подписи) или следующим "
    "сообщением."
)


@router.message(F.text == BTN_SUBMIT_INSIGHT, StateFilter(None))
async def start_insight(message: Message, state: FSMContext) -> None:
    await state.set_state(InsightForm.waiting_content)
    await message.answer(INSIGHT_PROMPT_TEXT, reply_markup=insight_start_kb())


@router.message(InsightForm.waiting_content, F.photo)
async def content_with_photo(message: Message, state: FSMContext) -> None:
    photo_file_id = message.photo[-1].file_id
    caption = message.caption.strip() if message.caption else None
    await state.update_data(photo_file_id=photo_file_id)

    if caption:
        await state.update_data(text=caption)
        await _show_confirmation(message, state)
        return

    await state.set_state(InsightForm.waiting_text_after_photo)
    await message.answer("Добавьте текстовое описание к этому фото:", reply_markup=insight_start_kb())


@router.message(InsightForm.waiting_text_after_photo, F.text)
async def text_after_photo(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text:
        await message.answer("Опишите хотя бы коротко, о чём инсайд:", reply_markup=insight_start_kb())
        return
    await state.update_data(text=text)
    await _show_confirmation(message, state)


@router.message(InsightForm.waiting_content, F.text)
async def content_text_only(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text:
        await message.answer("Опишите хотя бы коротко, о чём инсайд:", reply_markup=insight_start_kb())
        return
    await state.update_data(text=text, photo_file_id=None)
    await state.set_state(InsightForm.waiting_photo_optional)
    await message.answer(
        "Приложите фото объекта (по желанию) или нажмите «Пропустить».",
        reply_markup=insight_skip_photo_kb(),
    )


@router.message(InsightForm.waiting_photo_optional, F.photo)
async def photo_added_after_text(message: Message, state: FSMContext) -> None:
    await state.update_data(photo_file_id=message.photo[-1].file_id)
    await _show_confirmation(message, state)


@router.callback_query(InsightForm.waiting_photo_optional, F.data == "insight:skip_photo")
async def photo_skipped(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(photo_file_id=None)
    await callback.answer()
    await _show_confirmation(callback.message, state)


async def _show_confirmation(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(InsightForm.confirm)
    summary = (
        "👀 <b>Проверьте перед отправкой</b>\n\n"
        f"{esc(data.get('text'))}\n\n"
        f"Фото: {'приложено ✅' if data.get('photo_file_id') else 'нет'}\n\n"
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
async def confirm_insight(callback: CallbackQuery, state: FSMContext, bot: Bot, bots: list[Bot]) -> None:
    data = await state.get_data()
    insight_id = insights_repo.create_insight(
        user_id=callback.from_user.id,
        text=data.get("text") or "(без текста)",
        photo_file_id=data.get("photo_file_id"),
    )
    await state.clear()
    await callback.answer()

    admin = is_admin(callback.from_user.id)
    await callback.message.answer(
        "✅ Инсайд отправлен на проверку. Как только модератор его оценит, "
        "вам придёт уведомление о начисленных кредитах доверия.",
        reply_markup=main_menu_kb(is_admin=admin),
    )

    insight_row = insights_repo.get_insight(insight_id)
    notification_text = format_insight_notification(insight_row)
    photo_file_id = data.get("photo_file_id")
    # Caption у фото ограничен 1024 символами Telegram — длинные инсайды
    # уходят как фото без подписи + отдельное текстовое сообщение.
    caption_fits = photo_file_id and len(notification_text) <= CAPTION_LIMIT

    kb = rate_insight_kb(insight_id)
    for admin_id in config.ADMIN_IDS:
        delivered = False
        if photo_file_id:
            # file_id всегда валиден у "bot" — это тот же бот, что и принял
            # фото от пользователя. Проблема бывает не с файлом, а с самим
            # админом: он мог ни разу не запускать именно этого бота (см.
            # config.BETA_BOT_TOKEN) или заблокировать его — тогда падаем
            # ниже на кросс-бот текстовый фолбэк.
            try:
                if caption_fits:
                    await bot.send_photo(
                        admin_id, photo_file_id, caption=notification_text, reply_markup=kb
                    )
                else:
                    await bot.send_photo(admin_id, photo_file_id)
                    await bot.send_message(admin_id, notification_text, reply_markup=kb)
                delivered = True
            except (TelegramForbiddenError, TelegramBadRequest):
                pass

        if not delivered:
            text = notification_text
            if photo_file_id:
                # Фото жёстко привязано к конкретному боту — переслать его
                # через другого бота нельзя (та же ошибка "Wrong file
                # identifier", что и в архиве), поэтому админ получает хотя
                # бы текст с пометкой, где искать фото.
                text += "\n\n📷 К инсайду приложено фото — доступно через бота, куда его прислали."
            await send_message_to_user(bots, admin_id, text, reply_markup=kb)
