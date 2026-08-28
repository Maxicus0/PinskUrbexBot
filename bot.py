"""
bot.py — точка входа. Собирает Dispatcher из роутеров handlers/*,
создаёт схему БД при старте и запускает long polling.

Запуск: python bot.py (перед этим — см. README.md)
"""
import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

import config
from database import holidays_repo, users_repo
from database.init_db import ensure_schema
from handlers import (
    admin_add_object,
    admin_manage_objects,
    admin_panel,
    admin_rate_insight,
    archive,
    common,
    insight_submit,
)
from utils.bot_delivery import send_message_to_user
from utils.holidays import format_broadcast_text, get_active_holiday

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def _start_health_server() -> None:
    """Поднимает HTTP-заглушку на config.PORT.

    Render Web Service считает деплой рабочим, только если сервис слушает
    порт из переменной PORT — сам бот работает через long polling и HTTP
    ему не нужен, поэтому это чисто формальная заглушка для healthcheck'а
    (см. render.yaml: healthCheckPath: /health).
    """
    app = web.Application()
    async def handle_index(request: web.Request) -> web.Response:
        return web.Response(text="PinskUrbexBot is running")

    async def handle_health(request: web.Request) -> web.Response:
        return web.Response(text="OK")

    app.router.add_get("/", handle_index)
    app.router.add_get("/health", handle_health)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", config.PORT)
    await site.start()
    logger.info("HTTP-заглушка для Render слушает порт %s", config.PORT)


async def _send_holiday_broadcast_if_needed(bots: list[Bot]) -> None:
    """Если сегодня праздник (см. utils/holidays.py) и поздравление ещё не
    уходило — рассылает его всем, у кого есть профиль."""
    holiday = get_active_holiday()
    if not holiday:
        return

    if not holidays_repo.try_reserve_broadcast(datetime.now().date()):
        return  # на сегодня уже отправляли (например, после рестарта бота)

    text = format_broadcast_text(holiday)
    user_ids = users_repo.get_all_telegram_ids()
    logger.info("Праздничная рассылка (%s): %s получателей", holiday["date"], len(user_ids))

    sent = 0
    for telegram_id in user_ids:
        if await send_message_to_user(bots, telegram_id, text):
            sent += 1
        await asyncio.sleep(0.05)  # не упереться в лимиты Telegram на рассылку

    logger.info("Праздничная рассылка завершена: доставлено %s из %s", sent, len(user_ids))


async def _holiday_scheduler(bots: list[Bot]) -> None:
    """Проверяет календарь праздников сразу при старте бота, а затем каждый
    день в 00:05 — на случай, если бот работает без перезапуска сутками."""
    while True:
        try:
            await _send_holiday_broadcast_if_needed(bots)
        except Exception as e:
            logger.exception("Не удалось выполнить праздничную рассылку: %s", e)

        now = datetime.now()
        next_check = (now + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
        await asyncio.sleep((next_check - now).total_seconds())


async def main() -> None:
    ensure_schema()

    if not config.ADMIN_IDS:
        logger.warning(
            "ADMIN_IDS пуст — уведомления об инсайдах отправлять некому. "
            "Заполните ADMIN_IDS в .env."
        )

    # Ровно один активный бот за процесс — см. config.ACTIVE_BOT_TOKEN.
    mode_label = "БЕТА (локальный запуск)" if config.IS_BETA_MODE else "боевой"
    bots = [
        Bot(
            token=config.ACTIVE_BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
    ]

    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(common.router)
    dp.include_router(admin_rate_insight.router)
    dp.include_router(admin_add_object.router)
    dp.include_router(admin_manage_objects.router)
    dp.include_router(admin_panel.router)
    dp.include_router(archive.router)
    dp.include_router(insight_submit.router)

    await _start_health_server()
    asyncio.create_task(_holiday_scheduler(bots))

    for bot in bots:
        # drop_pending_updates=False: если Render усыпил инстанс, апдейты
        # (например /start), пришедшие пока бот спал, не должны потеряться
        # при рестарте.
        await bot.delete_webhook(drop_pending_updates=False)

    logger.info("Бот запущен (%s), начинаю polling…", mode_label)
    await dp.start_polling(*bots)


if __name__ == "__main__":
    asyncio.run(main())
