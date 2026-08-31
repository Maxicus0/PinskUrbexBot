"""keyboards/objects_kb.py — клавиатуры для раздела 'Архив'."""
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
from utils.formatting import format_object_teaser


def objects_list_kb(
    objects, user_credits: int, display_mode: str = config.DEFAULT_ARCHIVE_DISPLAY_MODE
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for obj in objects:
        builder.button(
            text=format_object_teaser(obj, user_credits, display_mode),
            callback_data=f"obj:{obj['id']}",
        )
    builder.adjust(1)
    return builder.as_markup()
