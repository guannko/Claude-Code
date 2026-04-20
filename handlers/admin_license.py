"""Управление лицензией Studio ONE — раздел в admin-панели."""

import logging
from aiogram import Router, Bot, F
from aiogram.types import (
    CallbackQuery, Message,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from database.license import get_license_status, activate_license
from services.permissions import is_admin
from services.sender import edit_menu
from states import AdminSettingsStates
from data.salon import SECTION_PHOTOS

logger = logging.getLogger(__name__)
router = Router()

# cfg_key sentinel для отличия от обычных настроек
_LICENSE_KEY = "__license__"


def _fmt_status(status: dict) -> str:
    mode = status.get("mode", "unknown")
    if mode == "licensed":
        days = status.get("days_left", 0)
        return (
            "✅ <b>Studio ONE — Лицензия активна</b>\n\n"
            f"📅 Действует ещё: <b>{days} дн.</b>\n\n"
            "Для продления обратитесь к разработчику: @Brain_Index"
        )
    elif mode == "trial":
        hours = status.get("hours_left", 0)
        d, h = divmod(hours, 24)
        time_str = f"{d} дн. {h} ч." if d > 0 else f"{h} ч."
        return (
            "🆓 <b>Studio ONE — Пробный период</b>\n\n"
            f"⏱ Осталось: <b>{time_str}</b>\n\n"
            "После окончания бот будет недоступен для клиентов.\n"
            "Получить лицензию: @Brain_Index"
        )
    elif mode == "expired":
        return (
            "🔴 <b>Пробный период истёк</b>\n\n"
            "Клиенты не могут пользоваться ботом.\n"
            "Введите лицензионный ключ для активации.\n\n"
            "Получить ключ: @Brain_Index"
        )
    return "📋 <b>Studio ONE — Лицензия</b>\n\nСтатус неизвестен."


def _license_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Ввести ключ активации", callback_data="license:enter_key")],
        [InlineKeyboardButton(text="◀️ Назад в панель", callback_data="adm:panel")],
    ])


@router.callback_query(F.data == "license:menu")
async def cb_license_menu(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return
    await state.clear()
    status = await get_license_status()
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        _fmt_status(status), _license_kb(),
        photo_url=SECTION_PHOTOS.get("admin"),
    )
    await callback.answer()


@router.callback_query(F.data == "license:enter_key")
async def cb_license_enter_key(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return
    await state.set_state(AdminSettingsStates.entering_value)
    await state.update_data(cfg_key=_LICENSE_KEY, cfg_msg_id=callback.message.message_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Отмена", callback_data="license:menu"),
    ]])
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        "🔑 <b>Введите лицензионный ключ</b>\n\n"
        "Формат: <code>STUDIO-XXXX-XXXX-XXXX</code>\n\n"
        "Ключ предоставляется разработчиком: @Brain_Index",
        kb, photo_url=SECTION_PHOTOS.get("admin"),
    )
    await callback.answer()
