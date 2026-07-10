"""
Панель мастера — отображается при /start если пользователь привязан как мастер.

callback_data:
  mst_panel:bookings   — список предстоящих записей
  mst_panel:schedule   — переход к управлению расписанием
  mst_panel:buffer     — настройка интервала между записями
  mst_buffer:set:{min} — установить интервал {min} минут
"""

import logging
from aiogram import Router, Bot, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from bot_db import get_master_by_telegram_id, get_upcoming_bookings_for_master, get_master_buffer, set_master_buffer
from services.sender import edit_menu
from data.salon import SECTION_PHOTOS
from keyboards import master_panel_kb

logger = logging.getLogger(__name__)
router = Router()

_STATUS_ICONS = {"new": "🟡", "confirmed": "✅", "cancelled": "❌", "rejected": "❌"}

_BUFFER_OPTIONS = [0, 15, 30, 45, 60, 90, 120]


async def build_master_panel_text(master: dict) -> str:
    """Текст главного экрана мастера."""
    master_id = master["master_id"]
    bookings = await get_upcoming_bookings_for_master(master_id, limit=3)

    lines = [f"👩‍🎨 <b>Панель мастера — {master['name']}</b>\n"]

    if bookings:
        lines.append("📋 <b>Ближайшие записи:</b>")
        for b in bookings:
            icon = _STATUS_ICONS.get(b.get("status", "new"), "🟡")
            lines.append(
                f"{icon} {b.get('date','—')} {b.get('time_start','')} — "
                f"{b['user_name']} ({b['service']})"
            )
    else:
        lines.append("📋 Записей пока нет.")

    return "\n".join(lines)


def _buffer_kb(master_id: str, current: int) -> InlineKeyboardMarkup:
    """Клавиатура выбора интервала между записями."""
    rows = []
    row = []
    for mins in _BUFFER_OPTIONS:
        label = f"{'✅ ' if mins == current else ''}{mins} мин" if mins > 0 else f"{'✅ ' if mins == current else ''}Без интервала"
        row.append(InlineKeyboardButton(text=label, callback_data=f"mst_buffer:set:{mins}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="mst_panel:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "mst_panel:schedule")
async def cb_mst_panel_schedule(callback: CallbackQuery) -> None:
    master = await get_master_by_telegram_id(callback.from_user.id)
    if not master:
        await callback.answer("⛔ Вы не привязаны как мастер.", show_alert=True)
        return
    await callback.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Открыть расписание",
                              callback_data=f"adm_sch:master:{master['master_id']}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="mst_panel:home")],
    ])
    await edit_menu(
        callback.bot, callback.message.chat.id, callback.message.message_id,
        f"📅 <b>Расписание — {master['name']}</b>\n\nНажмите кнопку для редактирования:",
        kb, photo_url=SECTION_PHOTOS.get("masters"),
    )


@router.callback_query(F.data == "mst_panel:buffer")
async def cb_mst_panel_buffer(callback: CallbackQuery) -> None:
    master = await get_master_by_telegram_id(callback.from_user.id)
    if not master:
        await callback.answer("⛔ Вы не привязаны как мастер.", show_alert=True)
        return

    current = await get_master_buffer(master["master_id"])
    await edit_menu(
        callback.bot, callback.message.chat.id, callback.message.message_id,
        f"⏱ <b>Интервал между записями</b>\n\n"
        f"Текущий интервал: <b>{current} мин</b>\n\n"
        f"Выберите минимальную паузу после каждой записи.\n"
        f"Например: стрижка 30 мин + интервал 15 мин → следующая запись через 45 мин.",
        _buffer_kb(master["master_id"], current),
        photo_url=SECTION_PHOTOS.get("masters"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("mst_buffer:set:"))
async def cb_mst_buffer_set(callback: CallbackQuery, bot: Bot) -> None:
    master = await get_master_by_telegram_id(callback.from_user.id)
    if not master:
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    minutes = int(callback.data.split(":")[2])
    await set_master_buffer(master["master_id"], minutes)

    label = f"{minutes} мин" if minutes > 0 else "без интервала"
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        f"⏱ <b>Интервал между записями</b>\n\n"
        f"Текущий интервал: <b>{minutes} мин</b>\n\n"
        f"Выберите минимальную паузу после каждой записи.\n"
        f"Например: стрижка 30 мин + интервал 15 мин → следующая запись через 45 мин.",
        _buffer_kb(master["master_id"], minutes),
        photo_url=SECTION_PHOTOS.get("masters"),
    )
    await callback.answer(f"✅ Интервал установлен: {label}")


@router.callback_query(F.data == "mst_panel:home")
async def cb_mst_panel_home(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    master = await get_master_by_telegram_id(callback.from_user.id)
    if not master:
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return
    await state.clear()
    from bot_db import get_user_lang
    lang = await get_user_lang(callback.from_user.id)
    text = await build_master_panel_text(master)
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        text, master_panel_kb(lang),
        photo_url=master.get("photo_file_id") or SECTION_PHOTOS.get("masters"),
    )
    await callback.answer()
