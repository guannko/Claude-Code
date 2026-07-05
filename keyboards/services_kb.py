"""Клавиатуры для каталога услуг и записи на приём."""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


async def categories_kb() -> InlineKeyboardMarkup:
    from bot_db import get_categories
    categories = await get_categories()
    buttons = []
    for cat in categories:
        buttons.append([InlineKeyboardButton(
            text=cat["title"],
            callback_data=f"services:cat:{cat['cat_key']}",
        )])
    buttons.append([InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def services_browse_kb(category: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📅 Записаться", callback_data=f"book:start:{category}")],
        [
            InlineKeyboardButton(text="◀️ Назад",  callback_data="menu:services"),
            InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def services_list_kb(category: str, back_cb: str = "menu:services") -> InlineKeyboardMarkup:
    from bot_db import get_db_services_by_category
    items = await get_db_services_by_category(category)
    buttons = []
    for item in items:
        buttons.append([InlineKeyboardButton(
            text=f"{item['name']} — {item['price']}₽",
            callback_data=f"services:item:{item['service_id']}",
        )])
    buttons.append([
        InlineKeyboardButton(text="◀️ Назад",  callback_data=back_cb),
        InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def masters_kb(category: str, masters: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for m in masters:
        buttons.append([InlineKeyboardButton(
            text=m["name"],
            callback_data=f"book:master:{m['master_id']}",
        )])
    buttons.append([InlineKeyboardButton(text="👤 Любой мастер", callback_data="book:master:any")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"book:back_to_services:{category}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _fmt_duration(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} мин"
    hours = minutes / 60
    if hours == int(hours):
        return f"{int(hours)} ч"
    return f"{hours} ч"
