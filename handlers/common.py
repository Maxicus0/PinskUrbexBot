"""
handlers/common.py
--------------------
Базовые команды: /start, /cancel и вкладка "🎖 Мой уровень".

Плюс два предохранителя: "nav:menu" — универсальная кнопка "Назад" на
инлайн-клавиатурах, сбрасывающая FSM; menu_button_interrupt — перехват
кнопки главного меню посреди незавершённого сценария.
"""
from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
from database import users_repo
from keyboards.main_menu import (
    BTN_ADMIN_PANEL,
    BTN_ARCHIVE,
    BTN_MY_LEVEL,
    BTN_SUBMIT_INSIGHT,
    main_menu_kb,
)
from utils.access_control import is_admin
from utils.formatting import esc, format_level_card, plural_credits

router = Router(name="common")

_MENU_BUTTON_TEXTS = {BTN_ARCHIVE, BTN_SUBMIT_INSIGHT, BTN_MY_LEVEL, BTN_ADMIN_PANEL}


async def _has_active_state(message: Message, state: FSMContext) -> bool:
    """True, если у пользователя сейчас активен FSM-сценарий (иначе апдейт
    уходит дальше — обычным хендлерам кнопок меню со StateFilter(None))."""
    return await state.get_state() is not None


def _welcome_text(credits: int) -> str:
    return (
        f"👋 Добро пожаловать в архив заброшенных объектов города {esc(config.CITY_NAME)}.\n\n"
        "Это закрытая база: доступ к карточкам объектов открывается за "
        "<b>кредиты доверия</b>. Кредиты начисляются за инсайды — расскажите "
        "о новом объекте, его залазе, координатах или свежей новости, и "
        "модераторы оценят вашу информацию.\n\n"
        f"Сейчас у вас {credits} {plural_credits(credits)} доверия.\n"
        f"Нажмите «📤 Отправить инсайд», чтобы начать зарабатывать, или "
        f"«{BTN_MY_LEVEL}», чтобы увидеть свой прогресс."
    )


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = users_repo.get_or_create_user(
        message.from_user.id, message.from_user.username, message.from_user.full_name
    )
    admin = is_admin(message.from_user.id)
    await message.answer(_welcome_text(user["credits"]), reply_markup=main_menu_kb(is_admin=admin))


@router.message(Command("cancel"), StateFilter("*"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current is None:
        await message.answer("Нечего отменять.")
        return
    await state.clear()
    admin = is_admin(message.from_user.id)
    await message.answer("Действие отменено.", reply_markup=main_menu_kb(is_admin=admin))


@router.message(F.text == BTN_MY_LEVEL, StateFilter(None))
async def show_level(message: Message) -> None:
    credits = users_repo.get_credits(message.from_user.id)
    text = format_level_card(credits)
    await message.answer(text)


@router.callback_query(F.data == "nav:menu")
async def nav_to_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    """Универсальная кнопка "🔙 Назад" — сбрасывает FSM и открывает главное меню."""
    await state.clear()
    await callback.answer()
    admin = is_admin(callback.from_user.id)
    await callback.message.answer("🏠 Главное меню.", reply_markup=main_menu_kb(is_admin=admin))


@router.message(F.text.in_(_MENU_BUTTON_TEXTS), _has_active_state)
async def menu_button_interrupt(message: Message, state: FSMContext) -> None:
    """Нажатие кнопки главного меню посреди незавершённого сценария —
    сбрасывает FSM и сразу выполняет то, что попросил пользователь."""
    await state.clear()

    from handlers import admin_panel, archive, insight_submit  # ленивый импорт

    if message.text == BTN_ARCHIVE:
        await archive.open_archive(message)
    elif message.text == BTN_SUBMIT_INSIGHT:
        await insight_submit.start_insight(message, state)
    elif message.text == BTN_MY_LEVEL:
        await show_level(message)
    elif message.text == BTN_ADMIN_PANEL:
        await admin_panel.open_admin_panel(message)
