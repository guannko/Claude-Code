"""
Настройки салона для администратора.
Позволяет менять название, адрес, телефон, валюту и т.д. прямо из бота.
"""

import logging
from aiogram import Router, Bot, F
from aiogram.types import (
    CallbackQuery, Message,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from database import get_setting, set_setting, get_all_settings, log_action
from services.permissions import is_admin
from services.sender import edit_menu, send_menu
from states import AdminSettingsStates
from data.salon import SECTION_PHOTOS

logger = logging.getLogger(__name__)
router = Router()

# ── Ключи настроек с отображаемыми именами ────────────────

SETTINGS_META = [
    ("salon_name",            "🏷 Название салона"),
    ("salon_address",         "📍 Адрес"),
    ("salon_metro",           "🚇 Метро / ориентир"),
    ("salon_phone",           "📞 Телефон"),
    ("salon_instagram",       "📸 Instagram"),
    ("salon_hours_weekdays",  "⏰ Часы (будни)"),
    ("salon_hours_weekends",  "⏰ Часы (выходные)"),
    ("salon_since",           "📅 Год основания"),
    ("currency",              "💱 Символ валюты (₽/€/$)"),
    # Специалист
    ("specialist_label",  "👤 Специалист (ед.ч.)"),
    ("specialists_label", "👥 Специалисты (кнопка меню)"),
    # Фото секций (URL)
    ("photo_main",        "🖼 Фото: главная"),
    ("photo_services",    "🖼 Фото: услуги"),
    ("photo_masters",     "🖼 Фото: специалисты"),
    ("photo_booking",     "🖼 Фото: запись"),
    ("photo_about",       "🖼 Фото: о нас"),
    ("photo_admin",       "🖼 Фото: админ-панель"),
]


async def _build_settings_text(settings: dict) -> str:
    lines = ["⚙️ <b>Настройки салона</b>\n"]
    for key, label in SETTINGS_META:
        val = settings.get(key, "—")
        lines.append(f"  {label}: <code>{val}</code>")
    return "\n".join(lines)


def _settings_kb(is_owner_flag: bool = False) -> InlineKeyboardMarkup:
    rows = []
    for key, label in SETTINGS_META:
        rows.append([InlineKeyboardButton(
            text=f"✏️ {label}",
            callback_data=f"adm_cfg:edit:{key}",
        )])
    rows.append([InlineKeyboardButton(text="◀️ Назад в панель", callback_data="adm:panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── Показать меню настроек ────────────────────────────────

@router.callback_query(F.data == "adm_cfg:menu")
async def cb_adm_cfg_menu(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    await state.clear()
    settings = await get_all_settings()
    text = await _build_settings_text(settings)
    from services.permissions import is_owner as _is_owner
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        text, _settings_kb(_is_owner(callback.from_user.id)),
        photo_url=SECTION_PHOTOS.get("admin"),
    )
    await callback.answer()


# ── Начать редактирование одной настройки ─────────────────

@router.callback_query(F.data.startswith("adm_cfg:edit:"))
async def cb_adm_cfg_edit(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    key = callback.data.split(":", 2)[2]
    label = dict(SETTINGS_META).get(key, key)
    current = await get_setting(key, "")

    await state.set_state(AdminSettingsStates.entering_value)
    await state.update_data(cfg_key=key, cfg_msg_id=callback.message.message_id)

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Отмена", callback_data="adm_cfg:menu"),
    ]])
    hint = ""
    if key == "currency":
        hint = "\n\n<i>Примеры: ₽  €  $  £  ¥</i>"
    elif key.startswith("salon_hours"):
        hint = "\n\n<i>Пример: Пн–Пт: 10:00 – 21:00</i>"
    elif key == "salon_since":
        hint = "\n\n<i>Пример: 2018</i>"

    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        f"✏️ <b>{label}</b>\n\n"
        f"Текущее значение: <code>{current or '—'}</code>\n\n"
        f"Введите новое значение:{hint}",
        kb,
        photo_url=SECTION_PHOTOS.get("admin"),
    )
    await callback.answer()


# ── Получить новое значение ───────────────────────────────

@router.message(StateFilter(AdminSettingsStates.entering_value))
async def msg_adm_cfg_value(message: Message, bot: Bot, state: FSMContext) -> None:
    if not await is_admin(message.from_user.id):
        return

    new_value = (message.text or "").strip()
    if not new_value:
        try:
            await message.delete()
        except Exception:
            pass
        return

    data = await state.get_data()
    key = data.get("cfg_key", "")
    msg_id = data.get("cfg_msg_id")
    await state.clear()

    await set_setting(key, new_value)
    await log_action(message.from_user.id, "setting_change", target=key,
                     details=f"→ {new_value[:80]}")

    try:
        await message.delete()
    except Exception:
        pass

    label = dict(SETTINGS_META).get(key, key)
    settings = await get_all_settings()
    text = await _build_settings_text(settings)

    if msg_id:
        try:
            await edit_menu(
                bot, message.chat.id, msg_id,
                f"✅ <b>{label}</b> сохранено!\n\n" + text,
                _settings_kb(),
                photo_url=SECTION_PHOTOS.get("admin"),
            )
            return
        except Exception:
            pass

    # Fallback — отправить новое сообщение
    try:
        new_msg = await bot.send_photo(
            chat_id=message.chat.id,
            photo=SECTION_PHOTOS.get("admin"),
            caption=f"✅ <b>{label}</b> сохранено!\n\n" + text,
            reply_markup=_settings_kb(),
            parse_mode="HTML",
        )
    except Exception:
        new_msg = await bot.send_message(
            chat_id=message.chat.id,
            text=f"✅ <b>{label}</b> сохранено!\n\n" + text,
            reply_markup=_settings_kb(),
            parse_mode="HTML",
        )
    from database import save_last_msg_id
    await save_last_msg_id(message.from_user.id, new_msg.message_id)
