"""Клавиатуры для флоу записи через мастеров."""

from datetime import date
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


DAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MONTHS_RU = ["", "янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]


async def master_categories_kb() -> InlineKeyboardMarkup:
    """Категории мастеров — динамически из DB."""
    from database import get_categories
    categories = await get_categories()
    buttons = []
    for cat in categories:
        buttons.append([InlineKeyboardButton(
            text=cat["title"],
            callback_data=f"mst:cat:{cat['cat_key']}",
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def masters_list_kb(masters: list[dict]) -> InlineKeyboardMarkup:
    """Список мастеров категории. По 2 кнопки в ряд."""
    buttons = []
    row = []
    for master in masters:
        row.append(InlineKeyboardButton(
            text=master["name"],
            callback_data=f"mst:pick:{master['master_id']}",
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([
        InlineKeyboardButton(text="◀️ Назад",  callback_data="mst:cats"),
        InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def master_services_kb(master_id: str, services: list[dict]) -> InlineKeyboardMarkup:
    """Услуги мастера. По 1 кнопке (названия длинные)."""
    buttons = []
    for svc in services:
        buttons.append([InlineKeyboardButton(
            text=f"{svc['name']} — {svc['price']}₽",
            callback_data=f"mst:svc:{master_id}:{svc['id']}",
        )])
    buttons.append([
        InlineKeyboardButton(text="◀️ Назад",  callback_data="mst:cats"),
        InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def master_dates_kb(dates: list[date], master_id: str, service_id: str) -> InlineKeyboardMarkup:
    """Кнопки с датами для мастер-флоу. По 2 в ряд."""
    buttons = []
    row = []
    for d in dates:
        label = f"{DAYS_RU[d.weekday()]} {d.day} {MONTHS_RU[d.month]}"
        row.append(InlineKeyboardButton(
            text=label,
            callback_data=f"mst:date:{master_id}:{service_id}:{d.isoformat()}",
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([
        InlineKeyboardButton(
            text="◀️ Назад",
            callback_data=f"mst:pick:{master_id}",
        ),
        InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def master_slots_kb(
    slots: list[str],
    master_id: str,
    service_id: str,
    date_str: str,
) -> InlineKeyboardMarkup:
    """Кнопки со свободными слотами для мастер-флоу. По 3 в ряд."""
    buttons = []
    row = []
    for s in slots:
        row.append(InlineKeyboardButton(
            text=s,
            callback_data=f"mst:slot:{master_id}:{service_id}:{date_str}:{s}",
        ))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([
        InlineKeyboardButton(
            text="◀️ Другая дата",
            callback_data=f"mst:svc:{master_id}:{service_id}",
        ),
        InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def master_confirm_kb(
    master_id: str,
    service_id: str,
    date: str,
    time: str,
) -> InlineKeyboardMarkup:
    """Кнопки подтверждения записи клиентом."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Подтвердить",
                callback_data=f"mst:confirm:{master_id}:{service_id}:{date}:{time}",
            ),
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data="mst:cancel",
            ),
        ]
    ])


def master_response_kb(booking_id: int, client_user_id: int) -> InlineKeyboardMarkup:
    """Кнопки для мастера: принять/отклонить."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Принять",
                callback_data=f"mst:approve:{booking_id}:{client_user_id}",
            ),
            InlineKeyboardButton(
                text="❌ Отклонить",
                callback_data=f"mst:reject:{booking_id}:{client_user_id}",
            ),
        ]
    ])
