"""Инлайн-клавиатуры раздела настроек."""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def settings_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"🌐 Язык: {'🇷🇺 RU' if lang == 'ru' else '🇬🇧 EN'}",
                callback_data="settings:lang"
            ),
        ],
        [
            InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main"),
        ],
    ])


def lang_choice_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
            InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en"),
        ],
        [
            InlineKeyboardButton(text="◀️ Назад",    callback_data="menu:settings"),
        ],
    ])
