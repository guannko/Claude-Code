"""
Отчёты для администратора.

callback_data:
  reports:menu        — выбор периода
  reports:week        — отчёт за 7 дней
  reports:month       — отчёт за 30 дней
  reports:quarter     — отчёт за 90 дней
"""

import logging
from aiogram import Router, Bot, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database import get_period_stats
from services.permissions import is_admin
from services.sender import edit_menu
from data.salon import SECTION_PHOTOS

logger = logging.getLogger(__name__)
router = Router()

_ADMIN_PHOTO = SECTION_PHOTOS.get("admin")


def _reports_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 7 дней",   callback_data="reports:week"),
            InlineKeyboardButton(text="📅 30 дней",  callback_data="reports:month"),
            InlineKeyboardButton(text="📅 90 дней",  callback_data="reports:quarter"),
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="adm:panel")],
    ])


def _back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ К отчётам", callback_data="reports:menu")],
        [InlineKeyboardButton(text="🏠 Панель",     callback_data="adm:panel")],
    ])


def _format_report(stats: dict) -> str:
    days = stats["days"]
    lines = [f"📈 <b>Отчёт за {days} дней</b>\n"]

    lines.append(f"📋 Всего записей: <b>{stats['bookings_total']}</b>")
    lines.append(f"✅ Подтверждено: <b>{stats['bookings_confirmed']}</b>")
    lines.append(f"👥 Новых клиентов: <b>{stats['new_clients']}</b>")

    if stats["avg_rating"] is not None:
        lines.append(f"⭐ Средний рейтинг: <b>{stats['avg_rating']}</b>")

    if stats["top_services"]:
        lines.append("\n🏆 <b>Топ услуги:</b>")
        for i, s in enumerate(stats["top_services"], 1):
            lines.append(f"  {i}. {s['service']} — {s['cnt']} записей")

    if stats["top_masters"]:
        lines.append("\n👩‍🎨 <b>Топ мастера:</b>")
        for i, m in enumerate(stats["top_masters"], 1):
            lines.append(f"  {i}. {m['master']} — {m['cnt']} записей")

    return "\n".join(lines)


@router.callback_query(F.data == "reports:menu")
async def cb_reports_menu(callback: CallbackQuery, bot: Bot) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        "📈 <b>Отчёты</b>\n\nВыберите период:",
        _reports_menu_kb(),
        photo_url=_ADMIN_PHOTO,
    )
    await callback.answer()


@router.callback_query(F.data.in_({"reports:week", "reports:month", "reports:quarter"}))
async def cb_reports_period(callback: CallbackQuery, bot: Bot) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    days_map = {"reports:week": 7, "reports:month": 30, "reports:quarter": 90}
    days = days_map[callback.data]

    stats = await get_period_stats(days)
    text = _format_report(stats)

    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        text, _back_kb(), photo_url=_ADMIN_PHOTO,
    )
    await callback.answer()
