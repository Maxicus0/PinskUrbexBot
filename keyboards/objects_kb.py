"""keyboards/objects_kb.py — клавиатуры для раздела 'Архив'."""
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from utils.formatting import format_object_teaser


def objects_list_kb(objects, user_credits: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for obj in objects:
        builder.button(
            text=format_object_teaser(obj, user_credits),
            callback_data=f"obj:{obj['id']}",
        )
    builder.adjust(1)
    return builder.as_markup()
