"""handlers/admin_panel.py — вход в админ-панель, список ожидающих инсайдов
и служебная функция 'изменить свои кредиты' (для тестов, только админам)."""
import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InputMediaPhoto, InputMediaVideo, Message

from database import insights_repo, users_repo
from keyboards.admin_menu import admin_menu_kb
from keyboards.insight_kb import rate_insight_kb
from keyboards.main_menu import BTN_ADMIN_PANEL
from states.admin_states import AdminSelfCreditsForm
from utils.access_control import is_admin
from utils.formatting import CAPTION_LIMIT, format_insight_notification, plural_credits

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
    """Не показывает список всех ожидающих инсайдов сразу — сразу же ведёт
    к оценке одного, самого старого (наибольший номер очереди, см.
    insights_repo.get_next_pending_insight и get_queue_position). После
    оценки этого инсайда админ автоматически переходит к следующему по
    порядку (см. handlers/admin_rate_insight.py, _advance_to_next_insight)
    — так вся очередь разбирается по одному инсайду за раз, без единого
    сообщения со списком и кучей кнопок."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Только для модераторов.", show_alert=True)
        return

    await callback.answer()
    total = insights_repo.count_pending_insights()
    if not total:
        await callback.message.answer("✅ Ожидающих инсайдов нет — всё разобрано.")
        return

    insight = insights_repo.get_next_pending_insight()
    queue_number = insights_repo.get_queue_position(insight["id"])
    await callback.message.answer(
        f"📋 Ожидающих инсайдов: {total}. Начинаем с самого старого "
        "(автор скрыт — оценка анонимная)."
    )
    await send_pending_insight(callback.message, insight, queue_number)


async def send_pending_insight(message: Message, insight, queue_number: int) -> None:
    """Показывает один ожидающий инсайд админу: медиа (если есть) + текст с
    кнопкой оценки. Общая логика для входа в очередь по кнопке «Ожидающие
    инсайды» (см. list_pending выше) и для автоматического перехода к
    следующему инсайду сразу после оценки текущего (см.
    handlers/admin_rate_insight.py, _advance_to_next_insight — так админ
    может разобрать всю очередь одну за другой, не возвращаясь в
    админ-панель вручную). Инсайды всегда показываются по одному, никогда
    все сразу."""
    text = format_insight_notification(insight, queue_number)
    kb = rate_insight_kb(insight["id"])
    media = insights_repo.get_insight_media(insight["id"])

    if not media:
        await message.answer(text, reply_markup=kb)
        return

    # Медиа раньше не показывалось в этом списке вообще — админ не мог
    # оценить инсайд с фото/видео, не найдя его сначала среди живых
    # уведомлений. Показываем так же, как при поступлении инсайда.
    try:
        if len(media) == 1:
            item = media[0]
            send = (
                message.answer_photo
                if item["media_type"] == "photo"
                else message.answer_video
            )
            if len(text) <= CAPTION_LIMIT:
                await send(item["file_id"], caption=text, reply_markup=kb)
            else:
                await send(item["file_id"])
                await message.answer(text, reply_markup=kb)
        else:
            # Медиагруппа не поддерживает reply_markup — кнопка оценки
            # уходит отдельным сообщением следом.
            items = [
                InputMediaVideo(media=m["file_id"])
                if m["media_type"] == "video"
                else InputMediaPhoto(media=m["file_id"])
                for m in media
            ]
            await message.answer_media_group(items)
            await message.answer(text, reply_markup=kb)
    except TelegramBadRequest as e:
        # file_id мог быть выдан другим ботом на этой же БД (см.
        # config.BETA_BOT_TOKEN) — не теряем инсайд, показываем текстом.
        logger.warning("Не удалось показать медиа инсайда #%s: %s", insight["id"], e)
        await message.answer(
            text + "\n\n📷 Медиа приложено, но недоступно через этого бота.",
            reply_markup=kb,
        )


@router.callback_query(F.data == "admin:set_own_credits")
async def start_set_own_credits(callback: CallbackQuery, state: FSMContext) -> None:
    """Служебная функция только для тестов: админ выставляет себе любое
    значение кредитов доверия, чтобы быстро проверить карточку уровня и
    пороги доступа объектов, не дожидаясь реальных инсайдов."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Только для модераторов.", show_alert=True)
        return

    current = users_repo.get_credits(callback.from_user.id)
    await state.set_state(AdminSelfCreditsForm.waiting_value)
    await callback.answer()
    await callback.message.answer(
        "🧪 <b>Тестовый режим — только для админов</b>\n\n"
        f"Текущий баланс: {current} {plural_credits(current)} доверия.\n"
        "Пришлите любое целое число — баланс будет выставлен ровно в это "
        "значение (не прибавится, а заменится)."
    )


@router.message(AdminSelfCreditsForm.waiting_value, F.text)
async def apply_set_own_credits(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        # Не должно случаться (в это состояние попадают только через
        # проверенную выше кнопку), но на всякий случай не выполняем.
        await state.clear()
        return

    raw = message.text.strip()
    if not raw.lstrip("-").isdigit():
        await message.answer("Нужно целое число. Попробуйте ещё раз:")
        return

    value = int(raw)
    new_balance = users_repo.set_credits(message.from_user.id, value)
    await state.clear()
    await message.answer(
        f"✅ Баланс выставлен: {new_balance} {plural_credits(new_balance)} доверия.",
        reply_markup=admin_menu_kb(),
    )
