"""
Панель мастера — отображается при /start если пользователь привязан как мастер.

callback_data:
  mst_panel:bookings   — список предстоящих записей
  mst_panel:schedule   — переход к управлению расписанием
"""

import logging
from aiogram import Router, Bot, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from database import get_master_by_telegram_id, get_upcoming_bookings_for_master
from services.permissions import is_admin
from services.sender import edit_menu
from data.salon import SECTION_PHOTOS
from keyboards import master_panel_kb

logger = logging.getLogger(__name__)
router = Router()

_STATUS_ICONS = {"new": "🟡", "confirmed": "✅", "cancelled": "❌", "rejected": "❌"}


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


@router.callback_query(F.data == "mst_panel:home")
async def cb_mst_panel_home(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    master = await get_master_by_telegram_id(callback.from_user.id)
    if not master:
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return
    await state.clear()
    from database import get_user_lang
    lang = await get_user_lang(callback.from_user.id)
    text = await build_master_panel_text(master)
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        text, master_panel_kb(lang),
        photo_url=master.get("photo_file_id") or SECTION_PHOTOS.get("masters"),
    )
    await callback.answer()
