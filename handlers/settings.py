"""
handlers/settings.py
----------------------
Команда /settings — личные настройки пользователя. Пока одна: режим
отображения объектов в списке "🗂 Архив" (обычная иконка 🗂 — выбрана по
умолчанию — или эмодзи фактического уровня опасности объекта вместо неё,
см. config.ARCHIVE_DISPLAY_MODES, utils.formatting.format_object_teaser).
Настройка личная и хранится на пользователя (users.archive_display_mode,
database/users_repo.py) — ни на кого другого не влияет.
"""
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
from database import users_repo
from keyboards.settings_kb import CALLBACK_PREFIX, archive_display_mode_kb

router = Router(name="settings")

_VALID_MODES = {code for code, _ in config.ARCHIVE_DISPLAY_MODES}
_MODE_PATTERN = "|".join(_VALID_MODES)


def _settings_text() -> str:
    return (
        "⚙️ <b>Настройки</b>\n\n"
        "Как показывать объекты в списке «🗂 Архив» — текущий вариант "
        "отмечен галочкой, нажмите на другой, чтобы переключиться:"
    )


@router.message(Command("settings"))
async def cmd_settings(message: Message, state: FSMContext) -> None:
    await state.clear()
    mode = users_repo.get_archive_display_mode(message.from_user.id)
    await message.answer(_settings_text(), reply_markup=archive_display_mode_kb(mode))


@router.callback_query(F.data.regexp(rf"^{CALLBACK_PREFIX}:({_MODE_PATTERN})$"))
async def set_archive_display_mode(callback: CallbackQuery) -> None:
    mode = callback.data.split(":", 2)[2]
    if mode not in _VALID_MODES:
        # Не должно случаться (regexp уже отфильтровал), но лучше мягкий
        # отказ, чем KeyError где-то ниже по цепочке.
        await callback.answer("Некорректный режим.", show_alert=True)
        return

    current = users_repo.get_archive_display_mode(callback.from_user.id)
    if mode == current:
        # Повторное нажатие на уже выбранный режим — ничего менять не нужно,
        # просто мягко подтверждаем всплывающей подсказкой.
        await callback.answer("Этот режим уже выбран.")
        return

    users_repo.set_archive_display_mode(callback.from_user.id, mode)
    await callback.answer("Режим обновлён.")
    await callback.message.answer(_settings_text(), reply_markup=archive_display_mode_kb(mode))
