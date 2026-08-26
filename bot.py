"""
bot.py — точка входа. Собирает Dispatcher из роутеров handlers/*,
создаёт схему БД при старте и запускает long polling.

Запуск: python bot.py (перед этим — см. README.md)
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

import config
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
    app.router.add_get("/", lambda _: web.Response(text="PinskUrbexBot is running"))
    app.router.add_get("/health", lambda _: web.Response(text="OK"))

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", config.PORT)
    await site.start()
    logger.info("HTTP-заглушка для Render слушает порт %s", config.PORT)


async def main() -> None:
    ensure_schema()

    if not config.ADMIN_IDS:
        logger.warning(
            "ADMIN_IDS пуст — уведомления об инсайдах отправлять некому. "
            "Заполните ADMIN_IDS в .env."
        )

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(common.router)
    dp.include_router(admin_rate_insight.router)
    dp.include_router(admin_add_object.router)
    dp.include_router(admin_manage_objects.router)
    dp.include_router(admin_panel.router)
    dp.include_router(archive.router)
    dp.include_router(insight_submit.router)

    await _start_health_server()

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот запущен, начинаю polling…")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
