"""
Умная отправка/редактирование фото-меню бота.
"""

import logging
from aiogram import Bot
from aiogram.types import Message, InlineKeyboardMarkup, InputMediaPhoto
from aiogram.exceptions import TelegramBadRequest
from bot_db import db

logger = logging.getLogger(__name__)


async def send_menu(
    message: Message,
    bot: Bot,
    text: str,
    reply_markup: InlineKeyboardMarkup,
    photo_url: str | None = None,
) -> None:
    user_id = message.from_user.id

    try:
        await message.delete()
    except Exception:
        pass

    last_id = await db.get_last_msg_id(user_id)
    if last_id:
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=last_id)
        except Exception:
            pass

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
            try:
                await bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=message_id,
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                )
            except TelegramBadRequest:
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
