"""
Умная отправка/редактирование фото-меню бота.

Вся навигация строится вокруг ОДНОГО фото-сообщения:
- send_menu()      — создать/заменить фото-сообщение (/start)
- edit_menu()      — изменить фото + подпись + кнопки (или только подпись+кнопки)
"""

import logging
from aiogram import Bot
from aiogram.types import Message, InlineKeyboardMarkup, InputMediaPhoto
from aiogram.exceptions import TelegramBadRequest
from database import db

logger = logging.getLogger(__name__)


async def send_menu(
    message: Message,
    bot: Bot,
    text: str,
    reply_markup: InlineKeyboardMarkup,
    photo_url: str | None = None,
) -> None:
    """
    Создаёт новое фото-сообщение меню (вызывается из /start).
    Старое сообщение удаляется перед созданием нового.
    """
    user_id = message.from_user.id

    # Удаляем /start сообщение пользователя
    try:
        await message.delete()
    except Exception:
        pass

    # Удаляем старое меню-сообщение
    last_id = await db.get_last_msg_id(user_id)
    if last_id:
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=last_id)
        except Exception:
            pass

    # Отправляем новое фото-сообщение
    if photo_url:
        try:
            new_msg = await bot.send_photo(
                chat_id=message.chat.id,
                photo=photo_url,
                caption=text,
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
            await db.save_last_msg_id(user_id, new_msg.message_id)
            return
        except Exception as e:
            logger.warning("send_menu: send_photo failed (%s), falling back to text", e)

    # Фолбэк — текстовое сообщение
    new_msg = await bot.send_message(
        chat_id=message.chat.id,
        text=text,
        reply_markup=reply_markup,
        parse_mode="HTML",
    )
    await db.save_last_msg_id(user_id, new_msg.message_id)


async def edit_menu(
    bot: Bot,
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup,
    photo_url: str | None = None,
) -> None:
    """
    Редактирует существующее фото-сообщение меню.
    - photo_url задан   → меняем фото + подпись + кнопки (edit_message_media)
    - photo_url = None  → меняем только подпись + кнопки (edit_message_caption)
    """
    try:
        if photo_url:
            await bot.edit_message_media(
                chat_id=chat_id,
                message_id=message_id,
                media=InputMediaPhoto(
                    media=photo_url,
                    caption=text,
                    parse_mode="HTML",
                ),
                reply_markup=reply_markup,
            )
        else:
            # Только подпись + кнопки (фото остаётся)
            try:
                await bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=message_id,
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                )
            except TelegramBadRequest:
                # Фолбэк: если вдруг текстовое сообщение
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            logger.warning("edit_menu: %s", e)
