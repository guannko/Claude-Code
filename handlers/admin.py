"""
Админ-панель. Доступна администраторам (ADMIN_ID и доп. админы из БД).
Управление администраторами — только для владельца (ADMIN_ID).
Команда /admin показывает inline-карточку со статистикой.
"""

import logging
from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from config import ADMIN_ID
from database import (
    get_users_count, get_today_users_count, get_last_user, get_recent_users,
    get_bookings_count, get_today_bookings_count, get_all_bookings,
    get_all_admins, add_admin, remove_admin,
    get_pending_bookings_count, get_pending_bookings,
    get_user_lang, get_user, get_audit_log,
)
from services.permissions import is_admin, is_owner
from services.sender import edit_menu, send_menu
from data.salon import SECTION_PHOTOS
from keyboards import admin_panel_kb, main_menu_with_admin_kb, main_menu_kb
from states import AdminStates

logger = logging.getLogger(__name__)
router = Router()


# ── Вспомогательные функции ─────────────────────────────────

def _admin_panel_kb(user_id: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="🔄 Обновить",     callback_data="admin:refresh"),
            InlineKeyboardButton(text="👥 Пользователи", callback_data="admin:users"),
        ],
        [
            InlineKeyboardButton(text="📅 Записи",       callback_data="admin:bookings"),
            InlineKeyboardButton(text="◀️ Закрыть",      callback_data="admin:close"),
        ],
        [
            InlineKeyboardButton(text="📅 Расписание мастеров", callback_data="adm_sch:list"),
        ],
        [
            InlineKeyboardButton(text="📸 Фото мастеров", callback_data="admin:master_photos"),
        ],
    ]
    if is_owner(user_id):
        rows.append([
            InlineKeyboardButton(text="👥 Администраторы", callback_data="admin:admins"),
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _admin_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="◀️ Назад", callback_data="admin:refresh"),
            InlineKeyboardButton(text="◀️ Закрыть", callback_data="admin:close"),
        ]
    ])


async def _build_admin_text() -> str:
    total = await get_users_count()
    today = await get_today_users_count()
    last = await get_last_user()
    bookings_total = await get_bookings_count()
    bookings_today = await get_today_bookings_count()

    if last:
        last_name = last.get("full_name") or last.get("username") or str(last.get("user_id"))
        last_time = (last.get("created_at") or "—")[:16].replace("T", " ")
    else:
        last_name = "—"
        last_time = "—"

    return (
        "🛠 <b>Панель администратора</b>\n\n"
        f"👥 Пользователей: <b>{total}</b>\n"
        f"📅 Сегодня новых: <b>{today}</b>\n"
        f"🕐 Последний вход: <b>{last_name}</b> (<code>{last_time}</code>)\n\n"
        f"📋 Записей всего: <b>{bookings_total}</b>\n"
        f"📅 Записей сегодня: <b>{bookings_today}</b>"
    )


async def _build_admin_panel_text(lang: str = "ru") -> str:
    """Текст для главного экрана фото-панели админа."""
    total = await get_users_count()
    today_users = await get_today_users_count()
    bookings_total = await get_bookings_count()
    bookings_today = await get_today_bookings_count()
    pending = await get_pending_bookings_count()

    if lang == "en":
        pending_str = f"🟡 <b>Awaiting confirmation: {pending}</b>\n\n" if pending else ""
        return (
            f"⚙️ <b>Admin panel</b>\n\n"
            f"{pending_str}"
            f"👥 Clients total: <b>{total}</b>  |  today: <b>{today_users}</b>\n"
            f"📋 Bookings total: <b>{bookings_total}</b>  |  today: <b>{bookings_today}</b>"
        )
    else:
        pending_str = f"🟡 <b>Ожидают подтверждения: {pending}</b>\n\n" if pending else ""
        return (
            f"⚙️ <b>Панель администратора</b>\n\n"
            f"{pending_str}"
            f"👥 Клиентов всего: <b>{total}</b>  |  сегодня: <b>{today_users}</b>\n"
            f"📋 Записей всего: <b>{bookings_total}</b>  |  сегодня: <b>{bookings_today}</b>"
        )


# ── Фото-панель: главный экран ──────────────────────────────

@router.callback_query(F.data == "adm:panel")
async def cb_adm_panel(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return
    await state.clear()
    lang = await get_user_lang(callback.from_user.id)
    text = await _build_admin_panel_text(lang)
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        text,
        admin_panel_kb(is_owner(callback.from_user.id), lang),
        photo_url=SECTION_PHOTOS.get("admin"),
    )
    await callback.answer()


# ── Фото-панель: клиентское меню для админа ─────────────────

@router.callback_query(F.data == "adm:client_view")
async def cb_adm_client_view(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return
    from texts import t
    await state.clear()
    lang = await get_user_lang(callback.from_user.id)
    user_db = await get_user(callback.from_user.id)
    name = (user_db or {}).get("full_name") or callback.from_user.first_name
    from database import get_setting
    salon_name = await get_setting("salon_name", "Салон красоты")
    from keyboards import main_menu_with_admin_kb as _mwakb
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        t("main_menu_text", lang, name=name, salon_name=salon_name),
        _mwakb(lang),
        photo_url=SECTION_PHOTOS.get("main"),
    )
    await callback.answer()


# ── Фото-панель: новые записи ───────────────────────────────

@router.callback_query(F.data == "adm:bookings_new")
async def cb_adm_bookings_new(callback: CallbackQuery, bot: Bot) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return
    bookings = await get_pending_bookings(limit=8)
    if not bookings:
        text = "✅ <b>Новых записей нет</b>\n\nВсе записи обработаны."
    else:
        lines = [f"🟡 <b>Новые записи ({len(bookings)})</b>\n"]
        for b in bookings:
            lines.append(
                f"🟡 <b>#{b['id']}</b> {b['service']}\n"
                f"   👤 {b['user_name']}  📅 {b.get('date', '—')} {b.get('time_start', '')}\n"
                f"   📞 {b.get('phone', '—')}"
            )
        text = "\n\n".join(lines)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="adm:bookings_new")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="adm:panel")],
    ])
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        text, kb, photo_url=SECTION_PHOTOS.get("admin"),
    )
    await callback.answer()


# ── Фото-панель: все записи ─────────────────────────────────

@router.callback_query(F.data == "adm:bookings_all")
async def cb_adm_bookings_all(callback: CallbackQuery, bot: Bot) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return
    bookings = await get_all_bookings(limit=8)
    status_icons = {"new": "🟡", "confirmed": "✅", "cancelled": "❌", "rejected": "❌"}
    if not bookings:
        text = "📋 <b>Записей нет</b>"
    else:
        lines = ["📋 <b>Последние записи</b>\n"]
        for b in bookings:
            icon = status_icons.get(b.get("status", "new"), "🟡")
            lines.append(
                f"{icon} <b>#{b['id']}</b> {b['service']}\n"
                f"   👤 {b['user_name']}  📅 {b.get('date_time', '—')}"
            )
        text = "\n\n".join(lines)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="adm:panel")],
    ])
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        text, kb, photo_url=SECTION_PHOTOS.get("admin"),
    )
    await callback.answer()


# ── Фото-панель: клиенты ────────────────────────────────────

@router.callback_query(F.data == "adm:users")
async def cb_adm_users(callback: CallbackQuery, bot: Bot) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return
    await _show_users_page(callback, bot, offset=0)
    await callback.answer()


@router.callback_query(F.data.startswith("adm:users_page:"))
async def cb_adm_users_page(callback: CallbackQuery, bot: Bot) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return
    offset = int(callback.data.split(":")[2])
    await _show_users_page(callback, bot, offset=offset)
    await callback.answer()


async def _show_users_page(callback, bot, offset: int = 0) -> None:
    from database import get_all_users_paginated, get_users_total_count
    PAGE = 8
    users = await get_all_users_paginated(limit=PAGE, offset=offset)
    total = await get_users_total_count()

    if not users:
        text = "👥 <b>Клиентов нет</b>"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="adm:panel")]
        ])
    else:
        text = f"👥 <b>Клиенты</b> ({total} всего)\n\nНажмите на клиента для управления:"
        rows = []
        for u in users:
            name = u.get("full_name") or u.get("username") or str(u.get("user_id"))
            rows.append([InlineKeyboardButton(
                text=name,
                callback_data=f"adm:user:{u['user_id']}",
            )])
        # Pagination
        nav = []
        if offset > 0:
            nav.append(InlineKeyboardButton(text="◀️", callback_data=f"adm:users_page:{max(0,offset-PAGE)}"))
        if offset + PAGE < total:
            nav.append(InlineKeyboardButton(text="▶️", callback_data=f"adm:users_page:{offset+PAGE}"))
        if nav:
            rows.append(nav)
        rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="adm:panel")])
        kb = InlineKeyboardMarkup(inline_keyboard=rows)

    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        text, kb, photo_url=SECTION_PHOTOS.get("admin"),
    )


@router.callback_query(F.data.startswith("adm:user:"))
async def cb_adm_user_card(callback: CallbackQuery, bot: Bot) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return
    user_id = int(callback.data[len("adm:user:"):])
    from database import get_user as _get_user, get_master_by_telegram_id
    u = await _get_user(user_id)
    if not u:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    master = await get_master_by_telegram_id(user_id)
    name = u.get("full_name") or u.get("username") or str(user_id)
    uname = f"@{u['username']}" if u.get("username") else "—"
    date = (u.get("created_at") or "—")[:10]
    master_status = f"👩‍🎨 Мастер: <b>{master['name']}</b> ({master.get('category','')})" if master else "👤 Статус: клиент"

    text = (
        f"👤 <b>{name}</b>\n\n"
        f"🔗 {uname}\n"
        f"🆔 <code>{user_id}</code>\n"
        f"📅 В системе с: {date}\n\n"
        f"{master_status}"
    )

    rows = []
    if not master:
        rows.append([InlineKeyboardButton(
            text="👩‍🎨 Назначить мастером",
            callback_data=f"adm:promote:{user_id}",
        )])
    else:
        rows.append([InlineKeyboardButton(
            text="👩‍🎨 Карточка мастера",
            callback_data=f"adm:master:{master['master_id']}",
        )])
    rows.append([InlineKeyboardButton(text="◀️ К списку", callback_data="adm:users")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)

    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        text, kb, photo_url=SECTION_PHOTOS.get("admin"),
    )
    await callback.answer()


# ── Фото-панель: статистика ─────────────────────────────────

@router.callback_query(F.data == "adm:stats")
async def cb_adm_stats(callback: CallbackQuery, bot: Bot) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return
    lang = await get_user_lang(callback.from_user.id)
    text = await _build_admin_panel_text(lang)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить" if lang == "ru" else "🔄 Refresh", callback_data="adm:stats")],
        [InlineKeyboardButton(text="◀️ Назад" if lang == "ru" else "◀️ Back", callback_data="adm:panel")],
    ])
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        text, kb, photo_url=SECTION_PHOTOS.get("admin"),
    )
    await callback.answer()


# ── История действий ────────────────────────────────────────

@router.callback_query(F.data == "adm:history")
async def cb_adm_history(callback: CallbackQuery, bot: Bot) -> None:
    if not await is_admin(callback.from_user.id):
        return await callback.answer()

    rows = await get_audit_log(limit=40)
    if not rows:
        text = "📋 <b>История действий</b>\n\nЗаписей пока нет."
    else:
        lines = ["📋 <b>История действий</b> (последние 40)\n"]
        for r in rows:
            ts = r["created_at"][:16]  # YYYY-MM-DD HH:MM
            icon = "✅" if r["status"] == "ok" else "❌"
            target = f" → {r['target']}" if r["target"] else ""
            details = f"\n    ↳ {r['details']}" if r["details"] else ""
            uid = r["user_id"]
            lines.append(f"{icon} <code>{ts}</code> [{uid}] <b>{r['action']}</b>{target}{details}")
        text = "\n".join(lines)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="adm:history")],
        [InlineKeyboardButton(text="◀️ Назад",    callback_data="adm:panel")],
    ])
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        text, kb, photo_url=SECTION_PHOTOS.get("admin"),
    )
    await callback.answer()


# ── Команда /admin ──────────────────────────────────────────

@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return

    text = await _build_admin_text()
    await message.answer(text, reply_markup=_admin_panel_kb(message.from_user.id))

    # Удаляем команду пользователя для чистоты чата
    try:
        await message.delete()
    except Exception:
        pass


# ── Callback: обновить панель ───────────────────────────────

@router.callback_query(F.data == "admin:refresh")
async def cb_admin_refresh(callback: CallbackQuery) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    text = await _build_admin_text()
    try:
        await callback.message.edit_text(text, reply_markup=_admin_panel_kb(callback.from_user.id))
    except Exception:
        pass  # текст не изменился — Telegram вернёт ошибку, игнорируем
    await callback.answer("✅ Обновлено")


# ── Callback: список пользователей ─────────────────────────

@router.callback_query(F.data == "admin:users")
async def cb_admin_users(callback: CallbackQuery) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    users = await get_recent_users(limit=10)
    if not users:
        text = "👥 <b>Пользователи</b>\n\nСписок пуст."
    else:
        lines = ["👥 <b>Последние пользователи</b>\n"]
        for i, u in enumerate(users, start=1):
            uid = u.get("user_id")
            name = u.get("full_name") or u.get("username") or str(uid)
            uname = f"@{u['username']}" if u.get("username") else "—"
            date = (u.get("created_at") or "—")[:10]
            lines.append(f"{i}. <b>{name}</b> ({uname})\n   🆔 <code>{uid}</code> · 📅 {date}")
        text = "\n".join(lines)

    await callback.message.edit_text(text, reply_markup=_admin_back_kb())
    await callback.answer()


# ── Callback: список записей ────────────────────────────────

@router.callback_query(F.data == "admin:bookings")
async def cb_admin_bookings(callback: CallbackQuery) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    bookings = await get_all_bookings(limit=10)
    if not bookings:
        text = "📅 <b>Записи</b>\n\nЗаписей пока нет."
    else:
        status_icons = {"new": "🟡", "confirmed": "✅", "cancelled": "❌"}
        lines = ["📅 <b>Последние записи</b>\n"]
        for b in bookings:
            icon = status_icons.get(b.get("status", "new"), "🟡")
            date = (b.get("created_at") or "—")[:10]
            lines.append(
                f"{icon} <b>#{b['id']}</b> {b['service']}\n"
                f"   👤 {b['user_name']}  🕐 {b['date_time']}\n"
                f"   📞 {b['phone']}  📅 {date}"
            )
        text = "\n\n".join(lines)

    await callback.message.edit_text(text, reply_markup=_admin_back_kb())
    await callback.answer()


# ── Callback: закрыть панель ────────────────────────────────

@router.callback_query(F.data == "admin:close")
async def cb_admin_close(callback: CallbackQuery) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()


# ══════════════════════════════════════════════════════════
#  Управление администраторами (только для владельца)
# ══════════════════════════════════════════════════════════

def _admins_list_kb(admins: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for a in admins:
        uid = a["user_id"]
        name = a.get("full_name") or a.get("username") or str(uid)
        rows.append([
            InlineKeyboardButton(
                text=f"❌ Удалить {name}",
                callback_data=f"admin:admin_remove:{uid}",
            )
        ])
    rows.append([
        InlineKeyboardButton(text="➕ Добавить админа", callback_data="admin:admin_add"),
        InlineKeyboardButton(text="◀️ Назад",           callback_data="admin:refresh"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "admin:admins")
async def cb_admin_admins(callback: CallbackQuery) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("⛔ Только для владельца.", show_alert=True)
        return

    admins = await get_all_admins()
    lines = ["👥 <b>Администраторы</b>\n"]
    if admins:
        for i, a in enumerate(admins, 1):
            uid = a["user_id"]
            name = a.get("full_name") or str(uid)
            uname = f"@{a['username']}" if a.get("username") else "без username"
            date = (a.get("created_at") or "—")[:10]
            lines.append(f"{i}. <b>{name}</b> ({uname})\n   🆔 <code>{uid}</code> · добавлен {date}")
    else:
        lines.append("Дополнительных администраторов нет.")

    text = "\n".join(lines)
    await callback.message.edit_text(text, reply_markup=_admins_list_kb(admins))
    await callback.answer()


@router.callback_query(F.data == "admin:admin_add")
async def cb_admin_admin_add(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("⛔ Только для владельца.", show_alert=True)
        return

    await state.set_state(AdminStates.entering_admin_id)
    await state.update_data(admin_msg_id=callback.message.message_id)

    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Отмена", callback_data="admin:admins"),
    ]])
    try:
        await callback.message.edit_text(
            "➕ <b>Добавить администратора</b>\n\n"
            "Введите один из вариантов:\n"
            "• @username — если этот человек уже использовал бота\n"
            "• числовой user_id — можно узнать через @userinfobot\n"
            "• Перешлите любое сообщение от него\n\n"
            "⚠️ По @username поиск работает только если человек уже запускал бота.",
            reply_markup=cancel_kb,
        )
    except Exception:
        pass
    await callback.answer()


@router.message(AdminStates.entering_admin_id)
async def msg_admin_entering_id(message: Message, bot: Bot, state: FSMContext) -> None:
    if not is_owner(message.from_user.id):
        return

    try:
        await message.delete()
    except Exception:
        pass

    data = await state.get_data()
    msg_id = data.get("admin_msg_id")
    chat_id = message.chat.id

    # Пробуем извлечь user_id: из пересланного сообщения или из текста
    new_user_id = None
    username = ""
    full_name = ""

    if message.forward_from:
        new_user_id = message.forward_from.id
        username = message.forward_from.username or ""
        full_name = message.forward_from.full_name or ""
    elif message.text:
        text = message.text.strip()
        try:
            new_user_id = int(text)
        except ValueError:
            if text.startswith("@"):
                uname = text.lstrip("@")
                from database import get_user_by_username
                found = await get_user_by_username(uname)
                if found:
                    new_user_id = found["user_id"]
                    username = found.get("username", uname)
                    full_name = found.get("full_name", "")
                else:
                    error_kb = InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="◀️ Отмена", callback_data="admin:admins"),
                    ]])
                    try:
                        await bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=msg_id,
                            text=f"❌ Пользователь {text} не найден в базе бота.\n\n⚠️ Поиск по @username работает только если человек уже запускал бота.",
                            reply_markup=error_kb,
                        )
                    except Exception:
                        pass
                    return
            else:
                error_kb = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="◀️ Отмена", callback_data="admin:admins"),
                ]])
                try:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=msg_id,
                        text="❌ Неверный формат. Введите @username, числовой user_id или перешлите сообщение.",
                        reply_markup=error_kb,
                    )
                except Exception:
                    pass
                return

    if new_user_id is None:
        return

    if new_user_id == ADMIN_ID:
        error_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀️ Отмена", callback_data="admin:admins"),
        ]])
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text="❌ Этот пользователь уже является владельцем.",
                reply_markup=error_kb,
            )
        except Exception:
            pass
        return

    await add_admin(new_user_id, username, full_name, message.from_user.id)
    await state.clear()

    # Показываем обновлённый список
    admins = await get_all_admins()
    lines = ["✅ <b>Администратор добавлен!</b>\n\n👥 <b>Администраторы</b>\n"]
    for i, a in enumerate(admins, 1):
        uid = a["user_id"]
        name = a.get("full_name") or str(uid)
        uname = f"@{a['username']}" if a.get("username") else "без username"
        date = (a.get("created_at") or "—")[:10]
        lines.append(f"{i}. <b>{name}</b> ({uname})\n   🆔 <code>{uid}</code> · добавлен {date}")
    text = "\n".join(lines)

    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=text,
            reply_markup=_admins_list_kb(admins),
            parse_mode="HTML",
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("admin:admin_remove:"))
async def cb_admin_remove(callback: CallbackQuery) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("⛔ Только для владельца.", show_alert=True)
        return

    user_id = int(callback.data.split(":")[2])
    await remove_admin(user_id)

    admins = await get_all_admins()
    lines = ["✅ <b>Администратор удалён.</b>\n\n👥 <b>Администраторы</b>\n"]
    if admins:
        for i, a in enumerate(admins, 1):
            uid = a["user_id"]
            name = a.get("full_name") or str(uid)
            uname = f"@{a['username']}" if a.get("username") else "без username"
            date = (a.get("created_at") or "—")[:10]
            lines.append(f"{i}. <b>{name}</b> ({uname})\n   🆔 <code>{uid}</code> · добавлен {date}")
    else:
        lines.append("Дополнительных администраторов нет.")

    text = "\n".join(lines)
    try:
        await callback.message.edit_text(text, reply_markup=_admins_list_kb(admins))
    except Exception:
        pass
    await callback.answer("✅ Удалён")


# ── Отмена FSM при нажатии "Назад" ─────────────────────────

@router.callback_query(AdminStates.entering_admin_id, F.data == "admin:admins")
async def cb_admin_cancel_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    admins = await get_all_admins()
    lines = ["👥 <b>Администраторы</b>\n"]
    if admins:
        for i, a in enumerate(admins, 1):
            uid = a["user_id"]
            name = a.get("full_name") or str(uid)
            uname = f"@{a['username']}" if a.get("username") else "без username"
            date = (a.get("created_at") or "—")[:10]
            lines.append(f"{i}. <b>{name}</b> ({uname})\n   🆔 <code>{uid}</code> · добавлен {date}")
    else:
        lines.append("Дополнительных администраторов нет.")
    text = "\n".join(lines)
    try:
        await callback.message.edit_text(text, reply_markup=_admins_list_kb(admins))
    except Exception:
        pass
    await callback.answer()
