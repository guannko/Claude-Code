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
from database import init_db, get_all_settings
from database.license import init_license_table, init_trial
from handlers import all_routers
from middlewares import LoggingMiddleware, ThrottlingMiddleware, LicenseMiddleware
from services.reminders import send_reminders, send_review_requests, send_birthday_greetings
from services.heartbeat import heartbeat_loop, set_offline


# ════════════════════════════════════════════════════════
#  Логирование
# ════════════════════════════════════════════════════════

os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════
#  Инициализация
# ════════════════════════════════════════════════════════

async def main() -> None:
    logger.info("Запуск бота...")

    await init_db()
    await init_license_table()   # Создать таблицу лицензии
    await init_trial()           # Запустить триал если ещё не запущен
    await get_all_settings()     # Прогреть кэш настроек (кнопки, фото и т.д.)

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.middleware(LoggingMiddleware())
    dp.message.middleware(ThrottlingMiddleware(throttle_time=2.0))
    dp.message.middleware(LicenseMiddleware())
    dp.callback_query.middleware(ThrottlingMiddleware())
    dp.callback_query.middleware(LicenseMiddleware())

    for router in all_routers:
        dp.include_router(router)

    # ── Планировщик напоминаний ─────────────────────────────
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(send_reminders,        CronTrigger(hour=14, minute=0), args=[bot], id="daily_reminders",       replace_existing=True)
    scheduler.add_job(send_review_requests,  CronTrigger(hour=10, minute=0), args=[bot], id="daily_review_requests", replace_existing=True)
    scheduler.add_job(send_birthday_greetings, CronTrigger(hour=9, minute=0), args=[bot], id="daily_birthdays",      replace_existing=True)
    scheduler.start()
    logger.info("Планировщик запущен: напоминания 14:00, отзывы 10:00, ДР 09:00")

    # ── Heartbeat → Supabase → Админка (real-time) ──────────────
    asyncio.create_task(heartbeat_loop())

    logger.info("Бот запущен. Ожидание сообщений...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await set_offline()
        scheduler.shutdown(wait=False)
        await bot.session.close()
        logger.info("Бот остановлен")


if __name__ == "__main__":
    asyncio.run(main())
