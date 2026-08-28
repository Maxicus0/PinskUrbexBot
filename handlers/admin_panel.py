"""handlers/admin_panel.py — вход в админ-панель и список ожидающих инсайдов."""
import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message

from database import insights_repo
from keyboards.admin_menu import admin_menu_kb
from keyboards.insight_kb import rate_insight_kb
from keyboards.main_menu import BTN_ADMIN_PANEL
from utils.access_control import is_admin
from utils.formatting import CAPTION_LIMIT, format_insight_notification

logger = logging.getLogger(__name__)

router = Router(name="admin_panel")


@router.message(F.text == BTN_ADMIN_PANEL, StateFilter(None))
async def open_admin_panel(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    await message.answer("🛠 Админ-панель", reply_markup=admin_menu_kb())


@router.callback_query(F.data == "admin:menu")
async def back_to_admin_menu(callback: CallbackQuery) -> None:
    """Кнопка «🔙 В админ-панель» из списка объектов (admin_objects_list_kb)."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Только для модераторов.", show_alert=True)
        return
    await callback.answer()
    await callback.message.answer("🛠 Админ-панель", reply_markup=admin_menu_kb())


@router.callback_query(F.data == "admin:pending")
async def list_pending(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Только для модераторов.", show_alert=True)
        return

    await callback.answer()
    pending = insights_repo.get_pending_insights()
    if not pending:
        await callback.message.answer("✅ Ожидающих инсайдов нет — всё разобрано.")
        return

    await callback.message.answer(
        f"📋 Ожидающих инсайдов: {len(pending)}. Ниже — каждый с кнопкой оценки "
        "(автор скрыт — оценка анонимная)."
    )
    for insight in pending:
        text = format_insight_notification(insight)
        kb = rate_insight_kb(insight["id"])
        photo_file_id = insight["photo_file_id"]

        if not photo_file_id:
            await callback.message.answer(text, reply_markup=kb)
            continue

        # Фото раньше не показывалось в этом списке вообще — админ не мог
        # оценить инсайд с фото, не найдя его сначала среди живых уведомлений.
        # Показываем так же, как при поступлении инсайда (см. insight_submit.py).
        try:
            if len(text) <= CAPTION_LIMIT:
                await callback.message.answer_photo(photo_file_id, caption=text, reply_markup=kb)
            else:
                await callback.message.answer_photo(photo_file_id)
                await callback.message.answer(text, reply_markup=kb)
        except TelegramBadRequest as e:
            # file_id мог быть выдан другим ботом на этой же БД (см.
            # config.BETA_BOT_TOKEN) — не теряем инсайд, показываем текстом.
            logger.warning("Не удалось показать фото инсайда #%s: %s", insight["id"], e)
            await callback.message.answer(
                text + "\n\n📷 Фото приложено, но недоступно через этого бота.",
                reply_markup=kb,
            )
