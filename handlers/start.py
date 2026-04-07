"""
/start — точка входа. Регистрирует пользователя, спрашивает имя, показывает меню.
"""

import logging
from aiogram import Router, Bot
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from config import DEFAULT_LANG, ADMIN_ID, WELCOME_PHOTO_URL
from database import (
    get_user, register_user, get_user_lang, get_users_count,
    save_last_msg_id, update_user_name, get_last_msg_id,
    mark_gdpr_accepted, delete_user_data, get_setting,
)
from keyboards import main_menu_kb, admin_panel_kb, main_menu_with_admin_kb
from services.sender import send_menu, edit_menu
from services.permissions import is_admin, is_owner
from states import RegistrationStates
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from data.salon import SECTION_PHOTOS

logger = logging.getLogger(__name__)
router = Router()

WELCOME_TEXT = (
    "💇‍♀️ <b>Добро пожаловать в Studio ONE!</b>\n\n"
    "Мы — салон красоты полного цикла на Арбате.\n"
    "Маникюр, стрижки, окрашивание, барбершоп — всё в одном месте.\n\n"
    "📍 ул. Арбат 24 (м. Арбатская)\n"
    "⏰ Пн–Пт 10:00–21:00 · Сб–Вс 10:00–20:00"
)

ASK_NAME_TEXT = (
    "💇‍♀️ <b>Добро пожаловать в Studio ONE!</b>\n\n"
    "📍 ул. Арбат 24 · ⏰ Пн–Пт 10–21, Сб–Вс 10–20\n\n"
    "👋 <b>Как вас зовут?</b>\n"
    "Введите ваше имя — мы будем знать как к вам обращаться:"
)


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot, state: FSMContext) -> None:
    user = message.from_user

    # Удаляем /start сообщение
    try:
        await message.delete()
    except Exception:
        pass

    await state.clear()
    main_photo = SECTION_PHOTOS.get("main", WELCOME_PHOTO_URL)

    # ── 1. Администратор ─────────────────────────────────────
    if await is_admin(user.id):
        await _ensure_registered(user)
        from handlers.admin import _build_admin_panel_text
        admin_lang = await get_user_lang(user.id)
        text = await _build_admin_panel_text(admin_lang)
        admin_photo = SECTION_PHOTOS.get("admin", main_photo)
        await send_menu(message, bot, text, admin_panel_kb(is_owner(user.id), admin_lang), photo_url=admin_photo)
        return

    # ── 2. Мастер ────────────────────────────────────────────
    from database import get_master_by_telegram_id
    from keyboards import master_panel_kb
    from handlers.master_panel import build_master_panel_text
    master = await get_master_by_telegram_id(user.id)
    if master and master.get("is_active", 1):
        await _ensure_registered(user)  # тихо регистрируем, без уведомления
        text = await build_master_panel_text(master)
        master_photo = master.get("photo_file_id") or SECTION_PHOTOS.get("masters")
        master_lang = await get_user_lang(user.id)
        await send_menu(message, bot, text, master_panel_kb(master_lang), photo_url=master_photo)
        return

    # ── 3. Клиент ────────────────────────────────────────────
    existing = await get_user(user.id)
    # Глобальный язык салона (устанавливается админом) как дефолт для новых пользователей
    salon_default_lang = await get_setting("default_lang", DEFAULT_LANG)
    tg_lang = (user.language_code or salon_default_lang)[:2]
    client_lang = tg_lang if tg_lang in ("ru", "en") else salon_default_lang
    from texts import t

    # Если нет в БД или не принял GDPR — показываем экран согласия
    needs_gdpr = (not existing) or (existing and not existing.get("gdpr_accepted"))
    if needs_gdpr:
        if not existing:
            await register_user(
                user_id=user.id, username=user.username or "",
                full_name="", lang=client_lang,
            )
        kb_gdpr = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=t("gdpr_accept_btn", client_lang),
                                 callback_data=f"gdpr:accept:{client_lang}"),
            InlineKeyboardButton(text=t("gdpr_decline_btn", client_lang),
                                 callback_data="gdpr:decline"),
        ]])
        try:
            gdpr_msg = await bot.send_photo(
                chat_id=message.chat.id, photo=main_photo,
                caption=t("gdpr_title", client_lang), reply_markup=kb_gdpr, parse_mode="HTML",
            )
        except Exception:
            gdpr_msg = await bot.send_message(
                chat_id=message.chat.id, text=t("gdpr_title", client_lang),
                reply_markup=kb_gdpr, parse_mode="HTML",
            )
        await save_last_msg_id(user.id, gdpr_msg.message_id)
        return

    # GDPR принят — показываем меню
    if not existing.get("full_name"):
        # Имя ещё не введено
        try:
            ask_msg = await bot.send_photo(
                chat_id=message.chat.id, photo=main_photo,
                caption=ASK_NAME_TEXT, parse_mode="HTML",
            )
        except Exception:
            ask_msg = await bot.send_message(
                chat_id=message.chat.id, text=ASK_NAME_TEXT, parse_mode="HTML",
            )
        await save_last_msg_id(user.id, ask_msg.message_id)
        await state.set_state(RegistrationStates.entering_name)
        await state.update_data(menu_msg_id=ask_msg.message_id)
    else:
        lang = existing.get("lang", "ru")
        salon_name = await get_setting("salon_name", "Салон красоты")
        stored_name = existing.get("full_name") or ""
        if stored_name:
            menu_text = f"✨ {t('welcome_back', lang, name=stored_name)}"
        else:
            menu_text = t("main_menu_text", lang, salon_name=salon_name)
        await send_menu(message, bot, menu_text, main_menu_kb(lang), photo_url=main_photo)


async def _ensure_registered(user) -> None:
    """Тихо регистрирует пользователя если его нет в users (без уведомлений)."""
    from database import get_user as _get_user
    if not await _get_user(user.id):
        await register_user(
            user_id=user.id,
            username=user.username or "",
            full_name=user.first_name or "",
            lang=DEFAULT_LANG,
        )


@router.message(RegistrationStates.entering_name)
async def msg_entering_name(message: Message, bot: Bot, state: FSMContext) -> None:
    name = message.text.strip() if message.text else ""
    if not name:
        try:
            await message.delete()
        except Exception:
            pass
        return

    await update_user_name(message.from_user.id, name)

    try:
        await message.delete()
    except Exception:
        pass

    data = await state.get_data()
    menu_msg_id = data.get("menu_msg_id")
    await state.clear()

    # Проверяем - если администратор, показываем панель
    if await is_admin(message.from_user.id):
        from handlers.admin import _build_admin_panel_text
        adm_lang = await get_user_lang(message.from_user.id)
        admin_text = await _build_admin_panel_text(adm_lang)
        adm_kb = admin_panel_kb(is_owner(message.from_user.id), adm_lang)
        if menu_msg_id:
            await edit_menu(
                bot, message.chat.id, menu_msg_id,
                admin_text, adm_kb,
                photo_url=SECTION_PHOTOS.get("admin"),
            )
            await save_last_msg_id(message.from_user.id, menu_msg_id)
        else:
            admin_photo = SECTION_PHOTOS.get("admin", WELCOME_PHOTO_URL)
            try:
                new_msg = await bot.send_photo(
                    chat_id=message.chat.id,
                    photo=admin_photo,
                    caption=admin_text,
                    reply_markup=adm_kb,
                    parse_mode="HTML",
                )
            except Exception:
                new_msg = await bot.send_message(
                    chat_id=message.chat.id,
                    text=admin_text,
                    reply_markup=adm_kb,
                    parse_mode="HTML",
                )
            await save_last_msg_id(message.from_user.id, new_msg.message_id)
        return

    # Если мастер (и не администратор)
    from database import get_master_by_telegram_id
    from keyboards import master_panel_kb
    from handlers.master_panel import build_master_panel_text
    master_rec = await get_master_by_telegram_id(message.from_user.id)
    if master_rec and master_rec.get("is_active", 1):
        master_text = await build_master_panel_text(master_rec)
        master_photo = master_rec.get("photo_file_id") or SECTION_PHOTOS.get("masters")
        mst_lang = await get_user_lang(message.from_user.id)
        if menu_msg_id:
            await edit_menu(
                bot, message.chat.id, menu_msg_id,
                master_text, master_panel_kb(mst_lang),
                photo_url=master_photo,
            )
            await save_last_msg_id(message.from_user.id, menu_msg_id)
        return

    # Обычный клиент
    from database import get_user_lang as _get_lang
    client_lang = await _get_lang(message.from_user.id)
    if client_lang == "en":
        greeting_text = f"✨ Nice to meet you, <b>{name}</b>!\n\nChoose a section 👇"
    else:
        greeting_text = f"✨ Приятно познакомиться, <b>{name}</b>!\n\nВыберите раздел 👇"

    if menu_msg_id:
        # Редактируем caption фото-сообщения (фото остаётся, добавляем кнопки)
        await edit_menu(
            bot, message.chat.id, menu_msg_id,
            greeting_text, main_menu_kb(client_lang),
            photo_url=None,  # фото не меняем
        )
        await save_last_msg_id(message.from_user.id, menu_msg_id)
    else:
        main_photo = SECTION_PHOTOS.get("main", WELCOME_PHOTO_URL)
        try:
            new_msg = await bot.send_photo(
                chat_id=message.chat.id,
                photo=main_photo,
                caption=greeting_text,
                reply_markup=main_menu_kb(client_lang),
                parse_mode="HTML",
            )
        except Exception:
            new_msg = await bot.send_message(
                chat_id=message.chat.id,
                text=greeting_text,
                reply_markup=main_menu_kb(client_lang),
                parse_mode="HTML",
            )
        await save_last_msg_id(message.from_user.id, new_msg.message_id)


# ── GDPR callbacks ──────────────────────────────────────────

from aiogram import F as _F
from aiogram.types import CallbackQuery


@router.callback_query(_F.data.startswith("gdpr:accept:"))
async def cb_gdpr_accept(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    from texts import t
    from database import update_user_lang
    lang = callback.data.split(":")[2]
    user = callback.from_user

    await mark_gdpr_accepted(user.id)
    await update_user_lang(user.id, lang)

    # Уведомление администратору
    if ADMIN_ID and user.id != ADMIN_ID:
        try:
            from database import get_system_lang
            sys_lang = await get_system_lang()
            count = await get_users_count()
            username_str = f"@{user.username}" if user.username else "—"
            notify_kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="✅ Принято" if sys_lang == "ru" else "✅ Acknowledged",
                    callback_data="adm_notify:dismiss:0",
                ),
                InlineKeyboardButton(
                    text="👥 Клиенты" if sys_lang == "ru" else "👥 Clients",
                    callback_data="adm:users",
                ),
            ]])
            if sys_lang == "en":
                notify_text = (
                    "👤 <b>New user!</b>\n"
                    f"├ ID: <code>{user.id}</code>\n"
                    f"├ Username: {username_str}\n"
                    f"└ Total users: <b>{count}</b>"
                )
            else:
                notify_text = (
                    "👤 <b>Новый пользователь!</b>\n"
                    f"├ ID: <code>{user.id}</code>\n"
                    f"├ Username: {username_str}\n"
                    f"└ Всего пользователей: <b>{count}</b>"
                )
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=notify_text,
                reply_markup=notify_kb,
                parse_mode="HTML",
            )
        except Exception:
            pass

    await state.set_state(RegistrationStates.entering_name)
    await state.update_data(menu_msg_id=callback.message.message_id, lang=lang)

    ask_text = (
        "👋 <b>Как вас зовут?</b>\n\nВведите ваше имя:"
        if lang == "ru" else
        "👋 <b>What's your name?</b>\n\nPlease enter your name:"
    )
    try:
        await bot.edit_message_caption(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            caption=ask_text, reply_markup=None, parse_mode="HTML",
        )
    except Exception:
        try:
            await bot.edit_message_text(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                text=ask_text, reply_markup=None, parse_mode="HTML",
            )
        except Exception:
            pass
    await callback.answer()


@router.callback_query(_F.data == "gdpr:decline")
async def cb_gdpr_decline(callback: CallbackQuery) -> None:
    from texts import t
    from database import get_user_lang
    lang = await get_user_lang(callback.from_user.id)
    text = t("gdpr_declined", lang)
    try:
        await callback.message.edit_caption(caption=text, parse_mode="HTML")
    except Exception:
        try:
            await callback.message.edit_text(text=text, parse_mode="HTML")
        except Exception:
            pass
    await callback.answer()
