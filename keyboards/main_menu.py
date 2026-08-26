"""keyboards/main_menu.py — главное меню (reply-клавиатура снизу экрана)."""
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_ARCHIVE = "🗂 Архив"
BTN_SUBMIT_INSIGHT = "📤 Отправить инсайд"
BTN_MY_LEVEL = "🎖 Мой уровень"
BTN_ADMIN_PANEL = "🛠 Админ-панель"


def main_menu_kb(is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=BTN_ARCHIVE), KeyboardButton(text=BTN_SUBMIT_INSIGHT)],
        [KeyboardButton(text=BTN_MY_LEVEL)],
    ]
    if is_admin:
        rows[-1].append(KeyboardButton(text=BTN_ADMIN_PANEL))
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)
