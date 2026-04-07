"""
Навигация по меню салона — через callback_query.
Одно сообщение редактируется при каждом нажатии кнопки.

Паттерн callback_data:
  "menu:main"        — главное меню
  "menu:services"    — каталог услуг (выбор категории)
  "menu:about"       — о салоне
  "menu:my_bookings" — мои записи
  "menu:ai_chat"     — AI-ассистент (вход в FSM)
  "menu:settings"    — настройки (из base template)
  "menu:profile"     — профиль (из base template)
  "menu:help"        — помощь (из base template)
  "settings:lang"    — выбор языка
  "lang:ru"          — установить язык
  "lang:en"          — установить язык
  "services:cat:{category}" — список услуг категории
"""

import logging
from aiogram import Router, Bot, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from database import (
    get_user, get_user_lang, update_user_lang,
    save_last_msg_id, get_last_msg_id, get_user_bookings,
    update_user_birthdate, get_user_visit_count,
    get_setting, mark_gdpr_accepted, delete_user_data,
    get_categories, get_category_by_key,
    get_db_services_by_category, get_masters_by_category,
)
from keyboards import (
    main_menu_kb, main_menu_with_admin_kb, settings_kb, lang_choice_kb,
    back_to_main_kb, categories_kb, services_browse_kb,
    master_categories_kb,
)
from services.sender import edit_menu
from states import AiChatStates, ProfileStates
from aiogram.filters import StateFilter
from texts import t
from data.salon import SECTION_PHOTOS

logger = logging.getLogger(__name__)
router = Router()


# ── Вспомогательная: текст каталога категории ─────────────

async def _build_services_text(category: str) -> str:
    cat = await get_category_by_key(category)
    if not cat:
        return "Категория не найдена."

    currency = await get_setting("currency", "₽")

    lines = [f"{cat['title']}\n"]
    items = await get_db_services_by_category(category)
    for i, item in enumerate(items):
        dur_min = item["duration"]
        if dur_min < 60:
            dur = f"{dur_min} мин"
        else:
            h = dur_min / 60
            dur = f"{int(h)} ч" if h == int(h) else f"{h} ч"

        prefix = "└" if i == len(items) - 1 else "├"
        lines.append(f"{prefix} {item['name']} — <b>{item['price']}{currency}</b> / {dur}")

    # Мастера из БД
    masters = await get_masters_by_category(category)
    if masters:
        lines.append("\n👥 <b>Мастера:</b>")
        for m in masters:
            desc = m.get("description") or ""
            line = f"   • {m['name']}"
            if desc:
                line += f" — {desc}"
            lines.append(line)

    return "\n".join(lines)


# ── Главное меню ───────────────────────────────────────────

@router.callback_query(F.data == "menu:main")
async def cb_main(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    await state.clear()
    lang = await get_user_lang(callback.from_user.id)
    from services.permissions import is_admin as _is_admin
    salon_name = await get_setting("salon_name", "Салон красоты")
    if await _is_admin(callback.from_user.id):
        kb = main_menu_with_admin_kb(lang)
    else:
        kb = main_menu_kb(lang)
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        t("main_menu_text", lang, name=callback.from_user.first_name, salon_name=salon_name),
        kb,
        photo_url=SECTION_PHOTOS.get("main"),
    )
    await callback.answer()


# ── Мастера: выбор категории ───────────────────────────────

@router.callback_query(F.data == "menu:masters")
async def cb_masters(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    await state.clear()
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        "👩‍🎨 <b>Выберите категорию мастера:</b>",
        await master_categories_kb(),
        photo_url=SECTION_PHOTOS.get("masters"),
    )
    await callback.answer()


# ── О салоне ───────────────────────────────────────────────

@router.callback_query(F.data == "menu:about")
async def cb_about(callback: CallbackQuery, bot: Bot) -> None:
    lang = await get_user_lang(callback.from_user.id)
    text = t(
        "about", lang,
        salon_name=await get_setting("salon_name", "Studio ONE"),
        salon_address=await get_setting("salon_address", "—"),
        salon_metro=await get_setting("salon_metro", ""),
        salon_phone=await get_setting("salon_phone", "—"),
        salon_instagram=await get_setting("salon_instagram", ""),
        salon_hours_weekdays=await get_setting("salon_hours_weekdays", "—"),
        salon_hours_weekends=await get_setting("salon_hours_weekends", "—"),
        salon_since=await get_setting("salon_since", "—"),
    )
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        text,
        back_to_main_kb(),
        photo_url=SECTION_PHOTOS.get("about"),
    )
    await callback.answer()


# ── Услуги: главная (выбор категории) ─────────────────────

@router.callback_query(F.data == "menu:services")
async def cb_services(callback: CallbackQuery, bot: Bot) -> None:
    lang = await get_user_lang(callback.from_user.id)
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        t("services_menu", lang),
        await categories_kb(),
        photo_url=SECTION_PHOTOS.get("services"),
    )
    await callback.answer()


# ── Услуги: конкретная категория (просмотр, без FSM) ───────

@router.callback_query(F.data.startswith("services:cat:"))
async def cb_services_category(callback: CallbackQuery, bot: Bot) -> None:
    category = callback.data.split(":")[2]
    text = await _build_services_text(category)
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        text,
        services_browse_kb(category),
        photo_url=SECTION_PHOTOS.get(category, SECTION_PHOTOS.get("services")),
    )
    await callback.answer()


# ── Мои записи ────────────────────────────────────────────

@router.callback_query(F.data == "menu:my_bookings")
async def cb_my_bookings(callback: CallbackQuery, bot: Bot) -> None:
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    lang = await get_user_lang(callback.from_user.id)
    bookings = await get_user_bookings(callback.from_user.id)

    inline_rows = []

    if not bookings:
        text = t("my_bookings_empty", lang)
    else:
        status_icons = {"new": "🟡", "confirmed": "✅", "cancelled": "❌"}
        lines = [t("my_bookings_header", lang)]
        for b in bookings[:10]:
            icon = status_icons.get(b["status"], "🟡")
            lines.append(
                f"{icon} <b>{b['service']}</b>\n"
                f"   👤 {b['master']}  📅 {b['date_time']}\n"
                f"   🆔 #{b['id']}"
            )
            # Кнопка редактирования — только для активных записей
            if b["status"] != "cancelled":
                inline_rows.append([
                    InlineKeyboardButton(
                        text=f"✏️ Ред. #{b['id']} — {b['service'][:20]}",
                        callback_data=f"mybooking:edit:{b['id']}",
                    )
                ])
        text = "\n\n".join(lines)

    inline_rows.append([
        InlineKeyboardButton(text="📅 Записаться", callback_data="book:start"),
        InlineKeyboardButton(text="◀️ Назад",      callback_data="menu:main"),
    ])

    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        text, InlineKeyboardMarkup(inline_keyboard=inline_rows),
        photo_url=SECTION_PHOTOS.get("mybookings"),
    )
    await callback.answer()


# ── AI-чат: вход ──────────────────────────────────────────

@router.callback_query(F.data == "menu:ai_chat")
async def cb_ai_chat_entry(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    lang = await get_user_lang(callback.from_user.id)
    await state.set_state(AiChatStates.waiting_question)
    await state.update_data(ai_msg_id=callback.message.message_id)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="ai:back")]
    ])
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        t("ai_chat_prompt", lang),
        kb,
        photo_url=SECTION_PHOTOS.get("ai"),
    )
    await callback.answer()


# ── Профиль ────────────────────────────────────────────────

@router.callback_query(F.data == "menu:profile")
async def cb_profile(callback: CallbackQuery, bot: Bot) -> None:
    user = callback.from_user
    lang = await get_user_lang(user.id)
    data = await get_user(user.id)
    visits = await get_user_visit_count(user.id)
    birthdate = (data or {}).get("birthdate") or "—"

    base_text = t(
        "profile_title", lang,
        user_id=data["user_id"],
        name=data["full_name"] or user.first_name,
        lang=data["lang"].upper(),
        created_at=data["created_at"][:10],
    )
    extra = (
        f"\n🎂 <b>{'День рождения' if lang == 'ru' else 'Birthday'}:</b> {birthdate}"
        f"\n🏆 <b>{'Посещений' if lang == 'ru' else 'Visits'}:</b> {visits}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🎂 Указать день рождения" if lang == "ru" else "🎂 Set birthday",
            callback_data="profile:set_birthday",
        )],
        [InlineKeyboardButton(
            text="🗑 Удалить мои данные" if lang == "ru" else "🗑 Delete my data",
            callback_data="profile:delete_data",
        )],
        [InlineKeyboardButton(text="◀️ Назад" if lang == "ru" else "◀️ Back",
                              callback_data="menu:main")],
    ])
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        base_text + extra, kb,
        photo_url=SECTION_PHOTOS.get("main"),
    )
    await callback.answer()


@router.callback_query(F.data == "profile:set_birthday")
async def cb_profile_set_birthday(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.set_state(ProfileStates.entering_birthdate)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Отмена", callback_data="menu:profile"),
    ]])
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        "🎂 Введите дату рождения в формате <b>ДД.ММ</b>\n"
        "Например: <code>15.03</code>",
        kb, photo_url=SECTION_PHOTOS.get("main"),
    )
    await callback.answer()


@router.message(StateFilter(ProfileStates.entering_birthdate))
async def msg_profile_birthdate(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    try:
        parts = raw.split(".")
        day = int(parts[0])
        month = int(parts[1])
        assert 1 <= day <= 31 and 1 <= month <= 12
        birthdate = f"{month:02d}-{day:02d}"
    except Exception:
        await message.answer("⚠️ Неверный формат. Введите дату как <b>ДД.ММ</b>, например: <code>25.12</code>",
                             parse_mode="HTML")
        return

    await update_user_birthdate(message.from_user.id, birthdate)
    await state.clear()
    try:
        await message.delete()
    except Exception:
        pass
    await message.answer(f"✅ День рождения сохранён: {raw} 🎂\n\nМы обязательно поздравим вас!")


# ── GDPR: удаление данных ─────────────────────────────────

@router.callback_query(F.data == "profile:delete_data")
async def cb_profile_delete_data(callback: CallbackQuery, bot: Bot) -> None:
    lang = await get_user_lang(callback.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="⚠️ Да, удалить" if lang == "ru" else "⚠️ Yes, delete",
            callback_data="profile:delete_confirm",
        )],
        [InlineKeyboardButton(
            text="◀️ Отмена" if lang == "ru" else "◀️ Cancel",
            callback_data="menu:profile",
        )],
    ])
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        t("gdpr_delete_confirm", lang),
        kb,
        photo_url=SECTION_PHOTOS.get("main"),
    )
    await callback.answer()


@router.callback_query(F.data == "profile:delete_confirm")
async def cb_profile_delete_confirm(callback: CallbackQuery, bot: Bot) -> None:
    lang = await get_user_lang(callback.from_user.id)
    await delete_user_data(callback.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="◀️ Назад" if lang == "ru" else "◀️ Back",
            callback_data="menu:main",
        )
    ]])
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        t("gdpr_deleted", lang),
        kb,
        photo_url=SECTION_PHOTOS.get("main"),
    )
    await callback.answer("✅")


# ── Быстрое переключение языка ────────────────────────────

@router.callback_query(F.data.startswith("lang:toggle:"))
async def cb_lang_toggle(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    new_lang = callback.data.split(":")[2]
    await update_user_lang(callback.from_user.id, new_lang)
    from services.permissions import is_admin as _is_admin, is_owner as _is_owner
    from keyboards import admin_panel_kb

    label = "🌐 " + ("English" if new_lang == "en" else "Русский")

    # Если мастер — остаёмся в панели мастера
    from database import get_master_by_telegram_id
    from keyboards import master_panel_kb
    master = await get_master_by_telegram_id(callback.from_user.id)
    if master and master.get("is_active", 1) and not await _is_admin(callback.from_user.id):
        from handlers.master_panel import build_master_panel_text
        text = await build_master_panel_text(master)
        master_photo = master.get("photo_file_id") or SECTION_PHOTOS.get("masters")
        await edit_menu(
            bot, callback.message.chat.id, callback.message.message_id,
            text, master_panel_kb(new_lang),
            photo_url=master_photo,
        )
        await callback.answer(label)
        return

    # Если переключение из админ-панели — остаёмся в панели + меняем глобальный язык
    if await _is_admin(callback.from_user.id):
        from database import set_setting
        await set_setting("default_lang", new_lang)   # глобальный язык салона
        msg_text = callback.message.caption or callback.message.text or ""
        if "Панель администратора" in msg_text or "Admin panel" in msg_text:
            from handlers.admin import _build_admin_panel_text
            text = await _build_admin_panel_text(new_lang)
            await edit_menu(
                bot, callback.message.chat.id, callback.message.message_id,
                text, admin_panel_kb(_is_owner(callback.from_user.id), new_lang),
                photo_url=SECTION_PHOTOS.get("admin"),
            )
            await callback.answer(label)
            return
        kb = main_menu_with_admin_kb(new_lang)
    else:
        kb = main_menu_kb(new_lang)

    salon_name = await get_setting("salon_name", "Салон красоты")
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        t("main_menu_text", new_lang,
          name=callback.from_user.first_name, salon_name=salon_name),
        kb,
        photo_url=SECTION_PHOTOS.get("main"),
    )
    await callback.answer(label)


# ── Настройки ──────────────────────────────────────────────

@router.callback_query(F.data == "menu:settings")
async def cb_settings(callback: CallbackQuery, bot: Bot) -> None:
    lang = await get_user_lang(callback.from_user.id)
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        t("settings_title", lang),
        settings_kb(lang),
        photo_url=SECTION_PHOTOS.get("main"),
    )
    await callback.answer()


@router.callback_query(F.data == "settings:lang")
async def cb_lang_choice(callback: CallbackQuery, bot: Bot) -> None:
    lang = await get_user_lang(callback.from_user.id)
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        t("settings_lang_prompt", lang),
        lang_choice_kb(),
        photo_url=SECTION_PHOTOS.get("main"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("lang:"))
async def cb_lang_set(callback: CallbackQuery, bot: Bot) -> None:
    new_lang = callback.data.split(":")[1]
    await update_user_lang(callback.from_user.id, new_lang)
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        t("settings_saved", new_lang),
        settings_kb(new_lang),
        photo_url=SECTION_PHOTOS.get("main"),
    )
    await callback.answer("✅")


# ── Помощь ─────────────────────────────────────────────────

@router.callback_query(F.data == "menu:help")
async def cb_help(callback: CallbackQuery, bot: Bot) -> None:
    lang = await get_user_lang(callback.from_user.id)
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        t("help_title", lang),
        back_to_main_kb(),
        photo_url=SECTION_PHOTOS.get("main"),
    )
    await callback.answer()


# ── Закрыть уведомление → обновить основное меню ───────────
#
# Используется когда бот отправляет клиенту отдельное текстовое
# сообщение (подтверждение/отмена записи от админа).
# Нажатие "В меню" удаляет это уведомление и обновляет
# постоянное фото-меню (по last_msg_id из БД).

@router.callback_query(F.data == "notify:dismiss")
async def cb_notify_dismiss(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    # Удаляем уведомление
    try:
        await callback.message.delete()
    except Exception:
        pass

    # Находим постоянное меню-сообщение
    last_msg_id = await get_last_msg_id(user_id)
    lang = await get_user_lang(user_id)
    await state.clear()

    salon_name = await get_setting("salon_name", "Салон красоты")
    menu_text = t("main_menu_text", lang, name=callback.from_user.first_name, salon_name=salon_name)
    from services.permissions import is_admin as _is_admin
    if await _is_admin(user_id):
        kb = main_menu_with_admin_kb(lang)
    else:
        kb = main_menu_kb(lang)

    if last_msg_id:
        # Обновляем постоянное меню на главный экран
        try:
            await edit_menu(
                bot, chat_id, last_msg_id,
                menu_text, kb,
                photo_url=SECTION_PHOTOS.get("main"),
            )
        except Exception:
            # Если постоянное сообщение недоступно — шлём новое
            new_msg = await bot.send_photo(
                chat_id=chat_id,
                photo=SECTION_PHOTOS.get("main"),
                caption=menu_text,
                reply_markup=kb,
                parse_mode="HTML",
            )
            await save_last_msg_id(user_id, new_msg.message_id)
    else:
        # Нет сохранённого меню — создаём новое
        new_msg = await bot.send_photo(
            chat_id=chat_id,
            photo=SECTION_PHOTOS.get("main"),
            caption=menu_text,
            reply_markup=kb,
            parse_mode="HTML",
        )
        await save_last_msg_id(user_id, new_msg.message_id)

    await callback.answer()
