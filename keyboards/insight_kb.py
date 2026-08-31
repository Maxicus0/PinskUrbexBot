"""keyboards/insight_kb.py — клавиатуры для сценария 'Отправить инсайд' и его оценки.

Кнопка "🔙 Назад" (callback_data="nav:menu") прерывает сценарий и
возвращает в главное меню — обрабатывается в handlers/common.py.
"""
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

NAV_MENU_CALLBACK = "nav:menu"
BACK_BUTTON_TEXT = "🔙 Назад"


def insight_start_kb() -> InlineKeyboardMarkup:
    """Клавиатура под самым первым сообщением сценария отправки инсайда."""
    builder = InlineKeyboardBuilder()
    builder.button(text=BACK_BUTTON_TEXT, callback_data=NAV_MENU_CALLBACK)
    return builder.as_markup()


def insight_media_kb() -> InlineKeyboardMarkup:
    """Клавиатура на этапе сбора медиа (фото/видео) инсайда: одна кнопка
    «Готово» работает и как «пропустить» (если медиа ещё нет), и как
    «закончить прикреплять» (если уже что-то добавлено)."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Готово", callback_data="insight:media_done")
    builder.button(text=BACK_BUTTON_TEXT, callback_data=NAV_MENU_CALLBACK)
    builder.adjust(1)
    return builder.as_markup()


def insight_confirm_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Отправить", callback_data="insight:confirm")
    builder.button(text="❌ Отмена", callback_data="insight:cancel")
    builder.adjust(2)
    return builder.as_markup()


def rating_back_kb() -> InlineKeyboardMarkup:
    """Кнопка под запросом числа кредитов доверия («Введите число кредитов
    доверия (0–N) за инсайд #X»). Открытие очереди («📋 Ожидающие инсайды»)
    сразу ведёт к этому запросу — отдельных кнопок «Оценить инсайд» и
    «Пропустить без оценки» больше нет (см. handlers/admin_rate_insight.py,
    present_insight_for_rating). «🔙 Назад в меню» прерывает оценку текущего инсайда
    без каких-либо изменений — он остаётся pending и просто ждёт своей
    очереди дальше (см. cancel_rating)."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад в меню", callback_data="rate:cancel")
    return builder.as_markup()
