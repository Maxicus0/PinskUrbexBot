"""
utils/bot_delivery.py
------------------------
Отправка сообщений/фото по telegram_id, перебирая список ботов по очереди до
первой успешной доставки. Обычно bots — список из одного активного бота (см.
config.ACTIVE_BOT_TOKEN), но пользователь мог быть создан ещё при другом
токене (например, раньше тестировался через бета-бота) — бот не может первым
написать тому, кто никогда не запускал именно его токен (Telegram ответит
Forbidden), отсюда и перебор.

Фото — отдельный случай: file_id жёстко привязан к тому боту, который принял
файл, так что отправка чужим ботом того же file_id закономерно упадёт с
"Wrong file identifier". Если не сработало ни у одного бота, вызывающий код
должен откатиться на текстовое уведомление.
"""
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

logger = logging.getLogger(__name__)

_DELIVERY_ERRORS = (TelegramForbiddenError, TelegramBadRequest)


async def send_message_to_user(bots, chat_id: int, text: str, **kwargs) -> bool:
    """Отправляет текстовое сообщение, перебирая ботов по очереди до первой
    успешной доставки. Возвращает True, если сообщение ушло хоть через
    одного бота."""
    for bot in bots:
        try:
            await bot.send_message(chat_id, text, **kwargs)
            return True
        except _DELIVERY_ERRORS:
            continue
    logger.warning(
        "Не удалось доставить сообщение %s ни одним из %d бота(ов)", chat_id, len(bots)
    )
    return False


async def send_photo_to_user(bots, chat_id: int, photo: str, **kwargs) -> Bot | None:
    """Отправляет фото по file_id, перебирая ботов. Реально сработает только
    у бота, который изначально принял этот файл, остальные закономерно
    получат TelegramBadRequest — это ожидаемое поведение, не баг.
    Возвращает бота, которым фото было успешно отправлено, либо None."""
    for bot in bots:
        try:
            await bot.send_photo(chat_id, photo, **kwargs)
            return bot
        except _DELIVERY_ERRORS:
            continue
    logger.warning(
        "Не удалось доставить фото %s ни одним из %d бота(ов)", chat_id, len(bots)
    )
    return None
