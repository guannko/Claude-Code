"""Общие клавиатуры."""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def back_to_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main")],
    ])


def back_and_home_kb(back_data: str, back_label: str = "◀️ Назад") -> InlineKeyboardMarkup:
    """Кнопки Назад + В меню в одной строке."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=back_label,   callback_data=back_data),
        InlineKeyboardButton(text="🏠 В меню",  callback_data="menu:main"),
    ]])
