"""
Сервис напоминаний, запросов отзывов и поздравлений.

Расписание планировщика (main.py):
  14:00 — send_reminders()       — напоминание о записи на завтра
  10:00 — send_review_requests() — запрос отзыва после вчерашнего визита
  09:00 — send_birthday_greetings() — поздравление с днём рождения
"""

import logging
from datetime import datetime

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import (
    get_bookings_for_tomorrow, get_bookings_for_review, mark_review_requested,
    get_birthday_users_today, get_user_visit_count,
)

logger = logging.getLogger(__name__)

# Дни недели на русском
_WEEKDAYS = ["понедельник", "вторник", "среду", "четверг", "пятницу", "субботу", "воскресенье"]


def _fmt_date_ru(date_str: str) -> str:
    """2026-04-01 → '1 апреля (среда)'"""
    _MONTHS = [
        "", "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря",
    ]
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{d.day} {_MONTHS[d.month]} ({_WEEKDAYS[d.weekday()]})"
    except Exception:
        return date_str


async def send_reminders(bot: Bot) -> None:
    """Отправить напоминания всем клиентам с записями на завтра."""
    bookings = await get_bookings_for_tomorrow()
    if not bookings:
        logger.info("Напоминания: записей на завтра нет")
        return

    sent = 0
    failed = 0
    for b in bookings:
        user_id = b.get("user_id")
        if not user_id:
            continue

        date_ru = _fmt_date_ru(b.get("date", ""))
        time_str = b.get("time_start", "")
        service = b.get("service", "—")
        master = b.get("master", "—")

        text = (
            "⏰ <b>Напоминание о записи</b>\n\n"
            f"Завтра вас ждём в <b>Studio ONE</b>!\n\n"
            f"💅 <b>Услуга:</b> {service}\n"
            f"👤 <b>Мастер:</b> {master}\n"
            f"📅 <b>Дата:</b> {date_ru}\n"
            f"🕐 <b>Время:</b> {time_str}\n\n"
            f"📍 ул. Арбат 24 (м. Арбатская)\n\n"
            "Если не сможете прийти — сообщите нам заранее:\n"
            "📞 +7 (495) 123-45-67"
        )

        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📋 Мои записи", callback_data="menu:my_bookings"),
            InlineKeyboardButton(text="🏠 Меню",        callback_data="notify:dismiss"),
        ]])

        try:
            await bot.send_message(
                chat_id=user_id,
                text=text,
                reply_markup=kb,
                parse_mode="HTML",
            )
            sent += 1
            logger.info("Напоминание отправлено: user_id=%s booking_id=%s", user_id, b.get("id"))
        except Exception as e:
            failed += 1
            logger.warning("Не удалось отправить напоминание user_id=%s: %s", user_id, e)

    logger.info("Напоминания отправлены: %d успешно, %d ошибок", sent, failed)


async def send_review_requests(bot: Bot) -> None:
    """Отправить запросы отзыва клиентам с вчерашними подтверждёнными записями."""
    bookings = await get_bookings_for_review()
    if not bookings:
        logger.info("Запросы отзывов: вчерашних записей без отзыва нет")
        return

    sent = 0
    failed = 0
    for b in bookings:
        user_id = b.get("user_id")
        if not user_id:
            continue

        service = b.get("service", "—")
        master = b.get("master", "—")
        booking_id = b["id"]

        text = (
            "🌸 <b>Как прошёл визит?</b>\n\n"
            f"Вы посетили <b>Studio ONE</b>\n"
            f"💅 <b>Услуга:</b> {service}\n"
            f"👤 <b>Мастер:</b> {master}\n\n"
            "Оцените наш сервис — это помогает нам становиться лучше!"
        )

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="⭐",     callback_data=f"review:rate:{booking_id}:1"),
                InlineKeyboardButton(text="⭐⭐",   callback_data=f"review:rate:{booking_id}:2"),
                InlineKeyboardButton(text="⭐⭐⭐", callback_data=f"review:rate:{booking_id}:3"),
            ],
            [
                InlineKeyboardButton(text="⭐⭐⭐⭐",   callback_data=f"review:rate:{booking_id}:4"),
                InlineKeyboardButton(text="⭐⭐⭐⭐⭐", callback_data=f"review:rate:{booking_id}:5"),
            ],
            [
                InlineKeyboardButton(text="Пропустить", callback_data=f"review:skip:{booking_id}"),
            ],
        ])

        try:
            await bot.send_message(
                chat_id=user_id,
                text=text,
                reply_markup=kb,
                parse_mode="HTML",
            )
            await mark_review_requested(booking_id)
            sent += 1
            logger.info("Запрос отзыва отправлен: user_id=%s booking_id=%s", user_id, booking_id)
        except Exception as e:
            failed += 1
            logger.warning("Не удалось отправить запрос отзыва user_id=%s: %s", user_id, e)

    logger.info("Запросы отзывов: %d отправлено, %d ошибок", sent, failed)


async def send_birthday_greetings(bot: Bot) -> None:
    """Поздравить пользователей с днём рождения и предложить скидку 15%."""
    users = await get_birthday_users_today()
    if not users:
        logger.info("Поздравления: сегодня именинников нет")
        return

    sent = 0
    for u in users:
        user_id = u.get("user_id")
        if not user_id:
            continue

        name = u.get("full_name") or "Дорогой гость"
        first_name = name.split()[0] if name else "Дорогой гость"

        text = (
            f"🎂 <b>С Днём Рождения, {first_name}!</b>\n\n"
            "Команда <b>Studio ONE</b> поздравляет вас с праздником!\n\n"
            "🎁 В честь вашего дня рождения дарим вам <b>скидку 15%</b> "
            "на любую услугу в течение 7 дней.\n\n"
            "Просто покажите это сообщение мастеру при записи.\n"
            "📞 Запись: +7 (495) 123-45-67"
        )

        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🎀 Записаться со скидкой", callback_data="book:start"),
        ]])

        try:
            await bot.send_message(
                chat_id=user_id,
                text=text,
                reply_markup=kb,
                parse_mode="HTML",
            )
            sent += 1
            logger.info("Поздравление отправлено: user_id=%s", user_id)
        except Exception as e:
            logger.warning("Не удалось отправить поздравление user_id=%s: %s", user_id, e)

    logger.info("Поздравления с ДР отправлены: %d", sent)
