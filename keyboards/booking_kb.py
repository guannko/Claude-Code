"""Клавиатуры для подтверждения/отмены записи и выбора слотов."""

from datetime import date
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


DAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MONTHS_RU = ["", "янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]


def dates_kb(dates: list[date], master_id: str) -> InlineKeyboardMarkup:
    """Кнопки с датами. По 2 в ряд."""
    buttons = []
    row = []
    for d in dates:
        label = f"{DAYS_RU[d.weekday()]} {d.day} {MONTHS_RU[d.month]}"
        row.append(InlineKeyboardButton(
            text=label,
            callback_data=f"book:date:{master_id}:{d.isoformat()}"
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([
        InlineKeyboardButton(text="◀️ Назад",  callback_data="book:back:master"),
        InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def slots_kb(slots: list[str], master_id: str, date_str: str) -> InlineKeyboardMarkup:
    """Кнопки со свободными слотами. По 3 в ряд."""
    buttons = []
    row = []
    for s in slots:
        row.append(InlineKeyboardButton(
            text=s,
            callback_data=f"book:slot:{master_id}:{date_str}:{s}"
        ))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([
        InlineKeyboardButton(
            text="◀️ Другая дата",
            callback_data=f"book:back:date:{master_id}",
        ),
        InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_booking_kb() -> InlineKeyboardMarkup:
    """Кнопки подтверждения и отмены записи."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="booking:confirm"),
            InlineKeyboardButton(text="❌ Отменить",    callback_data="booking:cancel"),
        ]
    ])


def after_booking_kb() -> InlineKeyboardMarkup:
    """Кнопки после успешной записи."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 Мои записи",  callback_data="menu:my_bookings"),
            InlineKeyboardButton(text="🏠 В меню",      callback_data="menu:main"),
        ]
    ])


def admin_booking_kb(booking_id: int) -> InlineKeyboardMarkup:
    """Кнопки для управления записью из уведомления администратору."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Подтвердить",
                callback_data=f"admin_booking:confirm:{booking_id}",
            ),
            InlineKeyboardButton(
                text="❌ Отменить",
                callback_data=f"admin_booking:cancel:{booking_id}",
            ),
        ]
    ])
