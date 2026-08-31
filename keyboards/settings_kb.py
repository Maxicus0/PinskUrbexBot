"""keyboards/settings_kb.py — клавиатура команды /settings."""
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config

CALLBACK_PREFIX = "settings:archmode"


def archive_display_mode_kb(current_mode: str) -> InlineKeyboardMarkup:
    """Все режимы отображения объектов архива (config.ARCHIVE_DISPLAY_MODES)
    одним списком — текущий помечен галочкой, нажатие на любой другой
    переключает на него (см. handlers/settings.py, set_archive_display_mode)."""
    builder = InlineKeyboardBuilder()
    for code, label in config.ARCHIVE_DISPLAY_MODES:
        prefix = "✅ " if code == current_mode else ""
        builder.button(text=f"{prefix}{label}", callback_data=f"{CALLBACK_PREFIX}:{code}")
    builder.adjust(1)
    return builder.as_markup()
