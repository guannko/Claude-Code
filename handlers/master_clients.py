"""
Панель мастера: клиенты, посещаемость, заметки.

callback_data:
  mst_clients:list                — список уникальных клиентов мастера
  mst_clients:client:{user_id}   — карточка клиента
  mst_clients:note:{user_id}     — редактировать заметку о клиенте
  mst_booking:{booking_id}       — карточка конкретной записи мастера
  mst_attend:{booking_id}:{val}  — отметить посещение (1=пришёл, 0=не пришёл)
"""

import logging
from aiogram import Router, Bot, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from database import (
    get_master_by_telegram_id, get_upcoming_bookings_for_master,
    get_user, get_user_bookings, save_client_note, get_client_note,
    update_booking_attended, get_booking, get_avg_rating, get_master_reviews,
)
from services.sender import edit_menu
from data.salon import SECTION_PHOTOS
from states import MasterNotesStates

logger = logging.getLogger(__name__)
router = Router()

_MASTER_PHOTO = SECTION_PHOTOS.get("masters")
_STATUS_ICONS = {"new": "🟡", "confirmed": "✅", "cancelled": "❌", "rejected": "❌"}


# ── Список клиентов мастера ─────────────────────────────────

@router.callback_query(F.data == "mst_clients:list")
async def cb_mst_clients_list(callback: CallbackQuery, bot: Bot) -> None:
    master = await get_master_by_telegram_id(callback.from_user.id)
    if not master:
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    bookings = await get_upcoming_bookings_for_master(master["master_id"], limit=50)

    # Уникальные клиенты (последние 50 записей)
    seen = {}
    for b in bookings:
        uid = b.get("user_id")
        if uid and uid not in seen:
            seen[uid] = b.get("user_name", str(uid))

    if not seen:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀️ Назад", callback_data="mst_panel:home"),
        ]])
        await edit_menu(
            bot, callback.message.chat.id, callback.message.message_id,
            f"👥 <b>{master['name']} — клиенты</b>\n\nЗаписей пока нет.",
            kb, photo_url=_MASTER_PHOTO,
        )
        await callback.answer()
        return

    rows = [
        [InlineKeyboardButton(text=f"👤 {name}", callback_data=f"mst_clients:client:{uid}")]
        for uid, name in seen.items()
    ]
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="mst_panel:home")])

    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        f"👥 <b>{master['name']} — клиенты</b>\n\nВсего: {len(seen)}",
        InlineKeyboardMarkup(inline_keyboard=rows),
        photo_url=_MASTER_PHOTO,
    )
    await callback.answer()


# ── Карточка клиента ────────────────────────────────────────

@router.callback_query(F.data.startswith("mst_clients:client:"))
async def cb_mst_client_card(callback: CallbackQuery, bot: Bot) -> None:
    master = await get_master_by_telegram_id(callback.from_user.id)
    if not master:
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    client_id = int(callback.data.split(":")[2])
    user = await get_user(client_id)
    user_bookings = await get_user_bookings(client_id)
    master_bookings = [b for b in user_bookings if b.get("master_id") == master["master_id"]]
    note = await get_client_note(master["master_id"], client_id)

    name = (user or {}).get("full_name") or str(client_id)
    phone = (user or {}).get("phone") or "—"
    visits = len([b for b in master_bookings if b.get("status") == "confirmed"])

    lines = [
        f"👤 <b>{name}</b>",
        f"📞 {phone}",
        f"✅ Посещений у вас: {visits}",
    ]
    if note:
        lines.append(f"\n📝 <b>Заметка:</b>\n{note}")
    else:
        lines.append("\n📝 <i>Заметок нет</i>")

    if master_bookings:
        lines.append("\n📋 <b>Последние записи:</b>")
        for b in master_bookings[:5]:
            icon = _STATUS_ICONS.get(b.get("status", "new"), "🟡")
            attended_icon = ""
            att = b.get("attended")
            if att == 1:
                attended_icon = " ✓"
            elif att == 0:
                attended_icon = " ✗"
            lines.append(f"{icon} {b.get('date','—')} {b.get('time_start','')} "
                         f"— {b['service']}{attended_icon}")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Добавить заметку",
                              callback_data=f"mst_clients:note:{client_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="mst_clients:list")],
    ])
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        "\n".join(lines), kb, photo_url=_MASTER_PHOTO,
    )
    await callback.answer()


# ── Заметка о клиенте ────────────────────────────────────────

@router.callback_query(F.data.startswith("mst_clients:note:"))
async def cb_mst_client_note(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    master = await get_master_by_telegram_id(callback.from_user.id)
    if not master:
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    client_id = int(callback.data.split(":")[2])
    existing = await get_client_note(master["master_id"], client_id)

    await state.set_state(MasterNotesStates.entering_note)
    await state.update_data(master_id=master["master_id"], client_id=client_id)

    hint = f"\n\nТекущая заметка:\n<i>{existing}</i>" if existing else ""
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Отмена",
                             callback_data=f"mst_clients:client:{client_id}"),
    ]])
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        f"📝 <b>Заметка о клиенте</b>{hint}\n\nНапишите заметку (цвет волос, аллергии, предпочтения):",
        kb, photo_url=_MASTER_PHOTO,
    )
    await callback.answer()


@router.message(StateFilter(MasterNotesStates.entering_note))
async def msg_master_note(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    master_id = data.get("master_id", "")
    client_id = data.get("client_id")

    note = message.text or ""
    await save_client_note(master_id, client_id, note)
    await state.clear()

    try:
        await message.delete()
    except Exception:
        pass
    await message.answer("✅ Заметка сохранена!")


# ── Посещаемость в списке записей ────────────────────────────

@router.callback_query(F.data.startswith("mst_panel:bookings"))
async def cb_mst_bookings_with_attendance(callback: CallbackQuery, bot: Bot) -> None:
    """Переопределяем список записей мастера с кнопками посещаемости."""
    master = await get_master_by_telegram_id(callback.from_user.id)
    if not master:
        await callback.answer("⛔ Вы не привязаны как мастер.", show_alert=True)
        return

    bookings = await get_upcoming_bookings_for_master(master["master_id"], limit=10)
    if not bookings:
        text = f"👩‍🎨 <b>{master['name']}</b>\n\n📋 Предстоящих записей нет."
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="mst_panel:bookings")],
            [InlineKeyboardButton(text="◀️ Назад",    callback_data="mst_panel:home")],
        ])
    else:
        lines = [f"👩‍🎨 <b>{master['name']} — записи</b>\n"]
        rows = []
        for b in bookings:
            icon = _STATUS_ICONS.get(b.get("status", "new"), "🟡")
            att = b.get("attended")
            att_text = " ✓" if att == 1 else (" ✗" if att == 0 else "")
            lines.append(
                f"{icon} <b>{b.get('date','—')} {b.get('time_start','')}</b>{att_text}\n"
                f"   👤 {b['user_name']} — {b['service']}\n"
                f"   📞 {b.get('phone','—')}"
            )
            # Кнопки отметки только для подтверждённых
            if b.get("status") == "confirmed":
                bid = b["id"]
                rows.append([
                    InlineKeyboardButton(
                        text=f"✓ Пришёл ({b.get('date','')[:5]})",
                        callback_data=f"mst_attend:{bid}:1"
                    ),
                    InlineKeyboardButton(
                        text="✗ Не пришёл",
                        callback_data=f"mst_attend:{bid}:0"
                    ),
                ])
        text = "\n\n".join(lines)
        rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="mst_panel:bookings")])
        rows.append([InlineKeyboardButton(text="◀️ Назад",    callback_data="mst_panel:home")])
        kb = InlineKeyboardMarkup(inline_keyboard=rows)

    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        text, kb, photo_url=_MASTER_PHOTO,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("mst_attend:"))
async def cb_mst_attend(callback: CallbackQuery, bot: Bot) -> None:
    parts = callback.data.split(":")
    booking_id = int(parts[1])
    attended = int(parts[2])

    booking = await get_booking(booking_id)
    if not booking:
        await callback.answer("Запись не найдена.", show_alert=True)
        return

    master = await get_master_by_telegram_id(callback.from_user.id)
    if not master or master["master_id"] != booking.get("master_id"):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    await update_booking_attended(booking_id, attended)
    mark = "✓ Пришёл" if attended == 1 else "✗ Не пришёл"
    await callback.answer(f"Отмечено: {mark}", show_alert=False)
    # Обновляем список
    await cb_mst_bookings_with_attendance(callback, bot)
