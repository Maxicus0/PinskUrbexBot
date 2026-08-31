"""keyboards/common_kb.py — клавиатуры базовых команд (сейчас — /about)."""
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

FAQ_ANON_CALLBACK = "about:faq_anon"


def about_kb() -> InlineKeyboardMarkup:
    """Клавиатура под текстом команды /about — пока один пункт FAQ."""
    builder = InlineKeyboardBuilder()
    builder.button(text="❓ Почему этот бот анонимен?", callback_data=FAQ_ANON_CALLBACK)
    return builder.as_markup()
