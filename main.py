"""
Точка входа бота.
Здесь: инициализация, подключение middlewares, роутеров, запуск polling.
"""

import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import BOT_TOKEN, LOG_PATH
from database import init_db
from handlers import all_routers
from middlewares import LoggingMiddleware, ThrottlingMiddleware
from services.reminders import send_reminders, send_review_requests, send_birthday_greetings


# ══════════════════════════════════════════════════════════
#  Логирование
# ══════════════════════════════════════════════════════════

os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(),                          # в консоль
        logging.FileHandler(LOG_PATH, encoding="utf-8"),  # в файл
    ],
)
logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════
#  Инициализация
# ══════════════════════════════════════════════════════════

async def main() -> None:
    logger.info("Запуск бота...")

    # База данных
    await init_db()

    # Bot + Dispatcher
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Middlewares (порядок важен)
    dp.message.middleware(LoggingMiddleware())
    dp.message.middleware(ThrottlingMiddleware(throttle_time=2.0))   # защита от дублей /start
    dp.callback_query.middleware(ThrottlingMiddleware())

    # Роутеры (common — последним, см. handlers/__init__.py)
    for router in all_routers:
        dp.include_router(router)

    # ── Планировщик напоминаний ────────────────────────────
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(
        send_reminders,
        trigger=CronTrigger(hour=14, minute=0),
        args=[bot],
        id="daily_reminders",
        replace_existing=True,
    )
    scheduler.add_job(
        send_review_requests,
        trigger=CronTrigger(hour=10, minute=0),
        args=[bot],
        id="daily_review_requests",
        replace_existing=True,
    )
    scheduler.add_job(
        send_birthday_greetings,
        trigger=CronTrigger(hour=9, minute=0),
        args=[bot],
        id="daily_birthdays",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Планировщик запущен: напоминания 14:00, отзывы 10:00, ДР 09:00")

    # Запуск
    logger.info("Бот запущен. Ожидание сообщений...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        logger.info("Бот остановлен")


if __name__ == "__main__":
    asyncio.run(main())
