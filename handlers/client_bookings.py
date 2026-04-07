"""
Управление своими записями клиентом.

callback_data:
  mybooking:edit:{id}    → детали записи + кнопки действий
  mybooking:cancel:{id}  → отменить запись
  mybooking:rebook:{id}  → отменить старую + начать новую запись
"""

import logging
from aiogram import Router, Bot, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from config import ADMIN_ID
from database import get_booking, update_booking_status, get_user_lang, get_system_lang
from services.sender import edit_menu
from data.salon import SECTION_PHOTOS

logger = logging.getLogger(__name__)
router = Router()


def _status_label(status: str) -> str:
    return {
        "new":       "🟡 Ожидает подтверждения",
        "confirmed": "✅ Подтверждена",
        "cancelled": "❌ Отменена",
    }.get(status, status)


# ── Детали записи + кнопки действий ──────────────────────────

@router.callback_query(F.data.startswith("mybooking:edit:"))
async def cb_mybooking_edit(callback: CallbackQuery, bot: Bot) -> None:
    booking_id = int(callback.data.split(":")[2])
    booking = await get_booking(booking_id)

    if not booking or booking["user_id"] != callback.from_user.id:
        await callback.answer("Запись не найдена.", show_alert=True)
        return

    if booking["status"] == "cancelled":
        await callback.answer("Эта запись уже отменена.", show_alert=True)
        return

    text = (
        f"✏️ <b>Редактирование записи #{booking_id}</b>\n\n"
        f"💅 {booking['service']}\n"
        f"👤 Мастер: {booking['master']}\n"
        f"📅 {booking['date']} в {booking['time_start']}\n"
        f"📞 Телефон: {booking['phone']}\n"
        f"Статус: {_status_label(booking['status'])}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📅 Изменить время",
                callback_data=f"mybooking:rebook:{booking_id}",
            ),
            InlineKeyboardButton(
                text="❌ Отменить запись",
                callback_data=f"mybooking:cancel:{booking_id}",
            ),
        ],
        [
            InlineKeyboardButton(text="◀️ Мои записи", callback_data="menu:my_bookings"),
        ],
    ])
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id, text, kb,
        photo_url=SECTION_PHOTOS.get("mybookings"),
    )
    await callback.answer()


# ── Отмена записи клиентом ────────────────────────────────────

@router.callback_query(F.data.startswith("mybooking:cancel:"))
async def cb_mybooking_cancel(callback: CallbackQuery, bot: Bot) -> None:
    booking_id = int(callback.data.split(":")[2])
    booking = await get_booking(booking_id)

    if not booking or booking["user_id"] != callback.from_user.id:
        await callback.answer("Запись не найдена.", show_alert=True)
        return

    if booking["status"] == "cancelled":
        await callback.answer("Запись уже отменена.", show_alert=True)
        return

    await update_booking_status(booking_id, "cancelled")

    # Уведомляем администратора — на системном языке
    if ADMIN_ID:
        try:
            sys_lang = await get_system_lang()
            adm_kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="✅ Принято" if sys_lang == "ru" else "✅ Acknowledged",
                    callback_data=f"adm_notify:dismiss:{booking_id}",
                ),
                InlineKeyboardButton(
                    text="📋 Все записи" if sys_lang == "ru" else "📋 All bookings",
                    callback_data="adm:bookings_all",
                ),
            ]])
            if sys_lang == "en":
                cancel_text = (
                    f"❌ <b>Client cancelled booking #{booking_id}</b>\n\n"
                    f"💅 {booking['service']}\n"
                    f"👤 Master: {booking['master']}\n"
                    f"📅 {booking['date']} at {booking['time_start']}\n"
                    f"👤 Client: {booking['user_name']} ({booking['username']})"
                )
            else:
                cancel_text = (
                    f"❌ <b>Клиент отменил запись #{booking_id}</b>\n\n"
                    f"💅 {booking['service']}\n"
                    f"👤 Мастер: {booking['master']}\n"
                    f"📅 {booking['date']} в {booking['time_start']}\n"
                    f"👤 Клиент: {booking['user_name']} ({booking['username']})"
                )
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=cancel_text,
                reply_markup=adm_kb,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning("Не удалось уведомить администратора: %s", e)

    from database import get_setting
    salon_phone = await get_setting("salon_phone", "+7 (495) 123-45-67")
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📅 Записаться снова", callback_data="book:start"),
        InlineKeyboardButton(text="🏠 В меню",           callback_data="menu:main"),
    ]])
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        (
            f"✅ <b>Запись #{booking_id} отменена.</b>\n\n"
            "Если нужно — запишитесь снова или позвоните нам:\n"
            f"📞 {salon_phone}"
        ),
        kb,
        photo_url=SECTION_PHOTOS.get("main"),
    )
    await callback.answer("❌ Запись отменена")


# ── Изменить время: отменяем старую → запускаем новую запись ─

@router.callback_query(F.data.startswith("mybooking:rebook:"))
async def cb_mybooking_rebook(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    from states import BookingStates
    from keyboards import categories_kb
    from texts import t

    booking_id = int(callback.data.split(":")[2])
    booking = await get_booking(booking_id)

    if not booking or booking["user_id"] != callback.from_user.id:
        await callback.answer("Запись не найдена.", show_alert=True)
        return

    # Отменяем старую запись
    await update_booking_status(booking_id, "cancelled")

    # Уведомляем администратора — на системном языке
    if ADMIN_ID:
        try:
            sys_lang = await get_system_lang()
            adm_kb2 = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="✅ Принято" if sys_lang == "ru" else "✅ Acknowledged",
                    callback_data=f"adm_notify:dismiss:{booking_id}",
                ),
                InlineKeyboardButton(
                    text="📋 Все записи" if sys_lang == "ru" else "📋 All bookings",
                    callback_data="adm:bookings_all",
                ),
            ]])
            if sys_lang == "en":
                rebook_text = (
                    f"🔄 <b>Client is rescheduling booking #{booking_id}</b>\n\n"
                    f"💅 {booking['service']}\n"
                    f"👤 Master: {booking['master']}\n"
                    f"📅 {booking['date']} at {booking['time_start']}\n"
                    f"👤 Client: {booking['user_name']} ({booking['username']})\n\n"
                    "Client is creating a new booking instead."
                )
            else:
                rebook_text = (
                    f"🔄 <b>Клиент изменяет запись #{booking_id}</b>\n\n"
                    f"💅 {booking['service']}\n"
                    f"👤 Мастер: {booking['master']}\n"
                    f"📅 {booking['date']} в {booking['time_start']}\n"
                    f"👤 Клиент: {booking['user_name']} ({booking['username']})\n\n"
                    "Клиент создаёт новую запись вместо этой."
                )
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=rebook_text,
                reply_markup=adm_kb2,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning("Не удалось уведомить администратора: %s", e)

    # Запускаем новый флоу записи
    lang = await get_user_lang(callback.from_user.id)
    await state.clear()
    await state.set_state(BookingStates.choosing_category)
    await state.update_data(menu_msg_id=callback.message.message_id)
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        t("booking_choose_category", lang),
        categories_kb(),
        photo_url=SECTION_PHOTOS.get("booking"),
    )
    await callback.answer("🔄 Создаём новую запись")


# ── Уведомление принято администратором ──────────────────────

@router.callback_query(F.data.startswith("adm_notify:dismiss:"))
async def cb_adm_notify_dismiss(callback: CallbackQuery) -> None:
    """Удаляет уведомление целиком после подтверждения."""
    from services.permissions import is_admin
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    try:
        await callback.message.delete()
    except Exception:
        # Если удалить не получилось — хотя бы убираем кнопки
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
    await callback.answer("✅ Принято")
