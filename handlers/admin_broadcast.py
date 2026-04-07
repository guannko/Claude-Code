"""
Рассылка сообщений всем пользователям бота.

callback_data:
  broadcast:start     — начать рассылку
  broadcast:confirm   — подтвердить отправку
  broadcast:cancel    — отмена
"""

import asyncio
import logging
from aiogram import Router, Bot, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from database import get_all_user_ids, get_users_count
from services.permissions import is_admin
from services.sender import edit_menu
from data.salon import SECTION_PHOTOS
from states import BroadcastStates

logger = logging.getLogger(__name__)
router = Router()

_ADMIN_PHOTO = SECTION_PHOTOS.get("admin")


@router.callback_query(F.data == "broadcast:start")
async def cb_broadcast_start(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    total = await get_users_count()
    await state.set_state(BroadcastStates.entering_message)

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Отмена", callback_data="adm:panel"),
    ]])
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        f"📣 <b>Рассылка</b>\n\n"
        f"Аудитория: <b>{total}</b> пользователей\n\n"
        "Напишите текст рассылки (поддерживается HTML).\n"
        "Можно прикрепить одно фото к тексту.",
        kb, photo_url=_ADMIN_PHOTO,
    )
    await callback.answer()


@router.message(StateFilter(BroadcastStates.entering_message))
async def msg_broadcast_text(message: Message, state: FSMContext, bot: Bot) -> None:
    text = message.text or message.caption or ""
    photo_id = None

    if message.photo:
        photo_id = message.photo[-1].file_id

    if not text and not photo_id:
        await message.answer("⚠️ Пожалуйста, отправьте текст или фото с подписью.")
        return

    await state.update_data(broadcast_text=text, broadcast_photo=photo_id)
    await state.set_state(BroadcastStates.confirming)

    try:
        await message.delete()
    except Exception:
        pass

    total = await get_users_count()
    preview = f"📣 <b>Рассылка — предпросмотр</b>\n\n{text}" if text else "📣 <b>Рассылка — предпросмотр</b>"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Отправить всем", callback_data="broadcast:confirm"),
            InlineKeyboardButton(text="❌ Отмена",          callback_data="broadcast:cancel"),
        ],
    ])

    # Показываем предпросмотр
    if photo_id:
        await bot.send_photo(
            chat_id=message.chat.id,
            photo=photo_id,
            caption=f"{preview}\n\n<i>Получателей: {total}</i>",
            reply_markup=kb,
            parse_mode="HTML",
        )
    else:
        await message.answer(
            f"{preview}\n\n<i>Получателей: {total}</i>",
            reply_markup=kb,
            parse_mode="HTML",
        )


@router.callback_query(F.data == "broadcast:confirm", StateFilter(BroadcastStates.confirming))
async def cb_broadcast_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    data = await state.get_data()
    text = data.get("broadcast_text", "")
    photo_id = data.get("broadcast_photo")
    await state.clear()

    user_ids = await get_all_user_ids()
    await callback.answer("📤 Рассылка запущена...", show_alert=False)

    # Редактируем сообщение — показываем прогресс
    try:
        await callback.message.edit_caption(
            caption=f"📤 <b>Рассылка запущена...</b>\n\nОтправляем {len(user_ids)} пользователям.",
            parse_mode="HTML",
        )
    except Exception:
        try:
            await callback.message.edit_text(
                f"📤 <b>Рассылка запущена...</b>\n\nОтправляем {len(user_ids)} пользователям.",
                parse_mode="HTML",
            )
        except Exception:
            pass

    sent = 0
    failed = 0
    for uid in user_ids:
        try:
            if photo_id:
                await bot.send_photo(chat_id=uid, photo=photo_id, caption=text,
                                     parse_mode="HTML")
            else:
                await bot.send_message(chat_id=uid, text=text, parse_mode="HTML")
            sent += 1
        except Exception as e:
            failed += 1
            logger.debug("broadcast to %s failed: %s", uid, e)
        await asyncio.sleep(0.05)  # ~20 msg/sec — в рамках лимитов Telegram

    logger.info("Рассылка завершена: %d отправлено, %d ошибок", sent, failed)

    # Итоговый отчёт
    result_text = (
        f"✅ <b>Рассылка завершена</b>\n\n"
        f"📤 Отправлено: {sent}\n"
        f"❌ Ошибок: {failed}"
    )
    try:
        await callback.message.edit_caption(caption=result_text, parse_mode="HTML")
    except Exception:
        try:
            await callback.message.edit_text(result_text, parse_mode="HTML")
        except Exception:
            await bot.send_message(chat_id=callback.message.chat.id,
                                   text=result_text, parse_mode="HTML")


@router.callback_query(F.data == "broadcast:cancel")
async def cb_broadcast_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Рассылка отменена.")
    try:
        await callback.message.delete()
    except Exception:
        pass
