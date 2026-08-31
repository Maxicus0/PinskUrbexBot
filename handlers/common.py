"""
handlers/common.py
--------------------
Базовые команды: /start, /cancel, /about и вкладка "🎖 Мой уровень".

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
from keyboards.common_kb import FAQ_ANON_CALLBACK, about_kb
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
        f"«{BTN_MY_LEVEL}», чтобы увидеть свой прогресс.\n\n"
        "Всю информацию о боте можно узнать из /about"
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


_NOT_OPEN_SOURCE_TEXT = (
    "🤖 <b>PinskUrbexBot</b>\n\n"
    "Кажется, автор совсем оборзел — сделал проект не опен-сорсным. "
    "Создатель бы такое точно не одобрил."
)


def _about_text() -> str:
    """Ссылка на GitHub берётся из config.GITHUB_REPO_URL (см. .env,
    render.yaml) — необязательная переменная: если она не заполнена, /about
    не падает и не ломает запуск бота, а просто честно об этом сообщает
    (см. _NOT_OPEN_SOURCE_TEXT). Отдельным блоком снизу — FAQ: пока в нём
    один пункт про анонимность, отвечает на него _faq_anon_text() по кнопке
    (см. about_kb())."""
    if not config.GITHUB_REPO_URL:
        body = _NOT_OPEN_SOURCE_TEXT
    else:
        body = (
            "🤖 <b>PinskUrbexBot</b>\n\n"
            "Исходный код проекта открыт — можно посмотреть и убедиться в его безопасности и ананимности:\n"
            f"<a href=\"{esc(config.GITHUB_REPO_URL)}\">{esc(config.GITHUB_REPO_URL)}</a>\n"
            "Всё расписано в README.md"
        )
    return body + "\n\nFQA:\nОтветы на частые вопросы — кнопкой ниже."


def _faq_anon_text() -> str:
    """Развёрнутый ответ на 'Почему этот бот анонимен?' — своими словами
    пересказывает раздел README «Безопасность и анонимность» (см. README.md,
    utils/crypto.py, handlers/archive.py, handlers/admin_rate_insight.py)."""
    text = (
        "🔒 <b>Почему этот бот анонимен?</b>\n\n"
        "Анонимность здесь — не одна галочка, а несколько независимых мер:\n\n"
        "📸 <b>Медиа бот не хранит и не скачивает.</b> К инсайду принимаются "
        "только фото/видео, отправленные как обычное медиа (не как файл) — "
        "в таком виде Telegram сам сжимает вложение и стирает служебные "
        "метаданные, включая GPS-координаты съёмки и модель устройства. В "
        "базе хранится только ссылка на файл на серверах Telegram (file_id), "
        "а не сами байты.\n\n"
        "🙈 <b>Админы оценивают инсайды вслепую.</b> При поступлении нового "
        "инсайда админ видит только счётчик очереди — без текста, медиа и уж "
        "тем более имени автора. Содержимое открывается, только когда админ "
        "сам заходит в очередь на оценку, и даже там имя, username и "
        "telegram_id автора не показываются никогда — оценка не может быть "
        "предвзятой к конкретному человеку.\n\n"
        "🔢 <b>Номер инсайда не выдаёт историю.</b> Это позиция в очереди "
        "ожидающих (от нового к старому), а не сквозной номер из базы — "
        "иначе он сам по себе говорил бы, сколько инсайдов вообще "
        "когда-либо прислали.\n\n"
        "🗑 <b>Инсайды не хранятся вечно.</b> Как только админ довёл оценку "
        "до конца, запись и все её медиа удаляются из базы навсегда — "
        "кредиты доверия при этом уже начислены и никуда не пропадают.\n\n"
        "🔐 <b>Личные данные в базе зашифрованы.</b> Telegram ID, username, "
        "полное имя и приватные заметки админов хранятся не открытым "
        "текстом, а в зашифрованном виде (AES-256). Тот, кто получит только "
        "дамп базы (бэкап, утечка у хостинга), не восстановит по нему ни "
        "одного человека — для этого нужен ещё и отдельный секретный ключ, "
        "который в саму базу никогда не попадает."
    )
    if config.GITHUB_REPO_URL:
        text += (
            "\n\n📖 <b>Всё это можно проверить.</b> Исходный код бота открыт "
            "— ссылка есть выше в /about."
        )
    return text


@router.message(Command("about"))
async def cmd_about(message: Message) -> None:
    await message.answer(_about_text(), reply_markup=about_kb())


@router.callback_query(F.data == FAQ_ANON_CALLBACK)
async def show_faq_anon(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(_faq_anon_text())


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
