"""
Управление мастерами в панели администратора.

callback_data схема:
  adm:masters                      — список всех мастеров
  adm:master:{master_id}           — карточка мастера
  adm:master_edit_name:{master_id} — редактировать имя
  adm:master_edit_desc:{master_id} — редактировать описание
  adm:master_edit_tg:{master_id}   — привязать TG аккаунт
  adm:master_toggle:{master_id}    — активировать/деактивировать
  adm:master_add                   — начать добавление нового мастера
  adm:master_photo:{master_id}     — уже есть в admin_masters.py, переиспользуем
"""

import logging
import re

from aiogram import Router, Bot, F
from aiogram.types import (
    CallbackQuery, Message,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext

from database import (
    get_all_masters_admin, get_master, update_master_name,
    update_master_description, set_master_telegram_id,
    toggle_master_active, add_master_to_db, get_user_by_username,
    get_master_schedule,
)
from services.permissions import is_admin
from services.sender import edit_menu
from data.salon import SECTION_PHOTOS
from states import AdminStates

logger = logging.getLogger(__name__)
router = Router()

_CAT_ICONS = {"manicure": "💅", "hair": "✂️", "barber": "🪒"}
_CAT_NAMES = {"manicure": "Маникюр", "hair": "Стрижки", "barber": "Барбер"}
_CAT_LIST  = ["manicure", "hair", "barber"]


# ── Helpers ────────────────────────────────────────────────

def _masters_list_kb(masters: list) -> InlineKeyboardMarkup:
    rows = []
    # Group by category
    seen_cats = []
    for m in masters:
        cat = m.get("category", "")
        if cat not in seen_cats:
            seen_cats.append(cat)
    for cat in seen_cats:
        cat_masters = [m for m in masters if m.get("category") == cat]
        for m in cat_masters:
            active = m.get("is_active", 1)
            icon = _CAT_ICONS.get(cat, "👩‍🎨")
            status = "✅" if active else "⛔"
            rows.append([InlineKeyboardButton(
                text=f"{icon} {status} {m['name']}",
                callback_data=f"adm:master:{m['master_id']}",
            )])
    rows.append([
        InlineKeyboardButton(text="➕ Добавить мастера", callback_data="adm:master_add"),
        InlineKeyboardButton(text="◀️ Назад",            callback_data="adm:panel"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _master_card_kb(master_id: str, has_tg: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="✏️ Имя",         callback_data=f"adm:master_edit_name:{master_id}"),
            InlineKeyboardButton(text="📝 Описание",    callback_data=f"adm:master_edit_desc:{master_id}"),
        ],
        [
            InlineKeyboardButton(text="📱 TG контакт",  callback_data=f"adm:master_edit_tg:{master_id}"),
            InlineKeyboardButton(text="📸 Фото",        callback_data=f"admin:master_photo:{master_id}"),
        ],
    ]
    if has_tg:
        rows.append([
            InlineKeyboardButton(text="🔗 Отвязать TG", callback_data=f"adm:master_unlink_tg:{master_id}"),
        ])
    rows += [
        [
            InlineKeyboardButton(text="📅 Расписание",  callback_data=f"adm_sch:master:{master_id}"),
            InlineKeyboardButton(text="🗑 Деактивировать", callback_data=f"adm:master_toggle:{master_id}"),
        ],
        [InlineKeyboardButton(text="◀️ К списку",       callback_data="adm:masters")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _master_card_text(m: dict) -> str:
    cat = m.get("category", "")
    icon = _CAT_ICONS.get(cat, "👩‍🎨")
    cat_name = _CAT_NAMES.get(cat, cat)
    active = "✅ Активен" if m.get("is_active", 1) else "⛔ Деактивирован"
    tg = f"<code>{m['telegram_user_id']}</code>" if m.get("telegram_user_id") else "❌ не привязан"
    desc = m.get("description") or "—"
    return (
        f"{icon} <b>{m['name']}</b>\n\n"
        f"📂 Категория: <b>{cat_name}</b>\n"
        f"📝 Описание: {desc}\n"
        f"📱 Telegram: {tg}\n"
        f"🔘 Статус: {active}"
    )


async def _build_masters_text(masters: list) -> str:
    lines = ["👩‍🎨 <b>Мастера</b>\n"]
    by_cat = {}
    for m in masters:
        by_cat.setdefault(m.get("category", "other"), []).append(m)
    for cat, ms in by_cat.items():
        icon = _CAT_ICONS.get(cat, "👩‍🎨")
        lines.append(f"{icon} <b>{_CAT_NAMES.get(cat, cat)}:</b>")
        for m in ms:
            s = "✅" if m.get("is_active", 1) else "⛔"
            tg = "📱" if m.get("telegram_user_id") else "  "
            lines.append(f"  {s} {tg} {m['name']}")
        lines.append("")
    return "\n".join(lines).rstrip()


# ── adm:masters — список мастеров ──────────────────────────

@router.callback_query(F.data == "adm:masters")
async def cb_adm_masters(callback: CallbackQuery, bot: Bot) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return
    masters = await get_all_masters_admin()
    text = await _build_masters_text(masters)
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        text, _masters_list_kb(masters),
        photo_url=SECTION_PHOTOS.get("masters"),
    )
    await callback.answer()


# ── adm:master:{id} — карточка мастера ─────────────────────

@router.callback_query(F.data.startswith("adm:master:"))
async def cb_adm_master_card(callback: CallbackQuery, bot: Bot) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return
    master_id = callback.data[len("adm:master:"):]
    m = await get_master(master_id)
    if not m:
        await callback.answer("Мастер не найден", show_alert=True)
        return
    photo = m.get("photo_file_id") or SECTION_PHOTOS.get("masters")
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        _master_card_text(m),
        _master_card_kb(master_id, has_tg=bool(m.get("telegram_user_id"))),
        photo_url=photo,
    )
    await callback.answer()


# ── adm:master_unlink_tg:{id} — отвязать TG ────────────────

@router.callback_query(F.data.startswith("adm:master_unlink_tg:"))
async def cb_adm_master_unlink_tg(callback: CallbackQuery, bot: Bot) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return
    master_id = callback.data[len("adm:master_unlink_tg:"):]
    await set_master_telegram_id(master_id, None)
    await callback.answer("✅ TG аккаунт отвязан", show_alert=True)
    m = await get_master(master_id)
    if m:
        photo = m.get("photo_file_id") or SECTION_PHOTOS.get("masters")
        await edit_menu(
            bot, callback.message.chat.id, callback.message.message_id,
            _master_card_text(m),
            _master_card_kb(master_id, has_tg=False),
            photo_url=photo,
        )


# ── adm:master_toggle:{id} — вкл/выкл мастера ─────────────

@router.callback_query(F.data.startswith("adm:master_toggle:"))
async def cb_adm_master_toggle(callback: CallbackQuery, bot: Bot) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return
    master_id = callback.data[len("adm:master_toggle:"):]
    new_val = await toggle_master_active(master_id)
    status = "активирован ✅" if new_val else "деактивирован ⛔"
    await callback.answer(f"Мастер {status}", show_alert=True)
    # Refresh card
    m = await get_master(master_id)
    if m:
        photo = m.get("photo_file_id") or SECTION_PHOTOS.get("masters")
        await edit_menu(
            bot, callback.message.chat.id, callback.message.message_id,
            _master_card_text(m),
            _master_card_kb(master_id),
            photo_url=photo,
        )


# ── adm:master_edit_name:{id} ──────────────────────────────

@router.callback_query(F.data.startswith("adm:master_edit_name:"))
async def cb_adm_edit_name(callback: CallbackQuery, state: FSMContext) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return
    master_id = callback.data[len("adm:master_edit_name:"):]
    m = await get_master(master_id)
    await state.set_state(AdminStates.master_editing_name)
    await state.update_data(editing_master_id=master_id, edit_msg_id=callback.message.message_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Отмена", callback_data=f"adm:master:{master_id}"),
    ]])
    try:
        await callback.message.edit_caption(
            f"✏️ <b>Новое имя для {m['name'] if m else master_id}</b>\n\nВведите имя:",
            reply_markup=kb, parse_mode="HTML",
        )
    except Exception:
        await callback.message.edit_text(
            f"✏️ <b>Новое имя для {m['name'] if m else master_id}</b>\n\nВведите имя:",
            reply_markup=kb, parse_mode="HTML",
        )
    await callback.answer()


@router.message(AdminStates.master_editing_name)
async def msg_master_edit_name(message: Message, bot: Bot, state: FSMContext) -> None:
    if not await is_admin(message.from_user.id):
        return
    data = await state.get_data()
    master_id = data.get("editing_master_id", "")
    msg_id = data.get("edit_msg_id")
    new_name = message.text.strip() if message.text else ""
    try:
        await message.delete()
    except Exception:
        pass
    if not new_name:
        return
    await update_master_name(master_id, new_name)
    await state.clear()
    m = await get_master(master_id)
    if m and msg_id:
        photo = m.get("photo_file_id") or SECTION_PHOTOS.get("masters")
        await edit_menu(
            bot, message.chat.id, msg_id,
            _master_card_text(m),
            _master_card_kb(master_id),
            photo_url=photo,
        )


# ── adm:master_edit_desc:{id} ──────────────────────────────

@router.callback_query(F.data.startswith("adm:master_edit_desc:"))
async def cb_adm_edit_desc(callback: CallbackQuery, state: FSMContext) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return
    master_id = callback.data[len("adm:master_edit_desc:"):]
    m = await get_master(master_id)
    await state.set_state(AdminStates.master_editing_description)
    await state.update_data(editing_master_id=master_id, edit_msg_id=callback.message.message_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Отмена", callback_data=f"adm:master:{master_id}"),
    ]])
    current = (m or {}).get("description") or "не задано"
    try:
        await callback.message.edit_caption(
            f"📝 <b>Описание для {(m or {}).get('name', master_id)}</b>\n\n"
            f"Сейчас: <i>{current}</i>\n\nВведите новое описание (специализация, стаж и т.д.):",
            reply_markup=kb, parse_mode="HTML",
        )
    except Exception:
        await callback.message.edit_text(
            f"📝 <b>Описание для {(m or {}).get('name', master_id)}</b>\n\n"
            f"Сейчас: <i>{current}</i>\n\nВведите новое описание:",
            reply_markup=kb, parse_mode="HTML",
        )
    await callback.answer()


@router.message(AdminStates.master_editing_description)
async def msg_master_edit_desc(message: Message, bot: Bot, state: FSMContext) -> None:
    if not await is_admin(message.from_user.id):
        return
    data = await state.get_data()
    master_id = data.get("editing_master_id", "")
    msg_id = data.get("edit_msg_id")
    new_desc = message.text.strip() if message.text else ""
    try:
        await message.delete()
    except Exception:
        pass
    if not new_desc:
        return
    await update_master_description(master_id, new_desc)
    await state.clear()
    m = await get_master(master_id)
    if m and msg_id:
        photo = m.get("photo_file_id") or SECTION_PHOTOS.get("masters")
        await edit_menu(
            bot, message.chat.id, msg_id,
            _master_card_text(m),
            _master_card_kb(master_id),
            photo_url=photo,
        )


# ── adm:master_edit_tg:{id} — привязать TG аккаунт ────────

@router.callback_query(F.data.startswith("adm:master_edit_tg:"))
async def cb_adm_edit_tg(callback: CallbackQuery, state: FSMContext) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return
    master_id = callback.data[len("adm:master_edit_tg:"):]
    m = await get_master(master_id)
    await state.set_state(AdminStates.master_editing_tg)
    await state.update_data(editing_master_id=master_id, edit_msg_id=callback.message.message_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Отмена", callback_data=f"adm:master:{master_id}"),
    ]])
    try:
        await callback.message.edit_caption(
            f"📱 <b>TG контакт для {(m or {}).get('name', master_id)}</b>\n\n"
            "Введите @username или user_id мастера,\n"
            "или перешлите любое его сообщение.\n\n"
            "⚠️ Поиск по @username работает если мастер уже запускал бота.",
            reply_markup=kb, parse_mode="HTML",
        )
    except Exception:
        await callback.message.edit_text(
            f"📱 <b>TG контакт для {(m or {}).get('name', master_id)}</b>\n\n"
            "Введите @username или user_id мастера,\n"
            "или перешлите любое его сообщение.\n\n"
            "⚠️ Поиск по @username работает если мастер уже запускал бота.",
            reply_markup=kb, parse_mode="HTML",
        )
    await callback.answer()


@router.message(AdminStates.master_editing_tg)
async def msg_master_edit_tg(message: Message, bot: Bot, state: FSMContext) -> None:
    if not await is_admin(message.from_user.id):
        return
    data = await state.get_data()
    master_id = data.get("editing_master_id", "")
    msg_id = data.get("edit_msg_id")
    try:
        await message.delete()
    except Exception:
        pass

    tg_user_id = None
    error_text = None

    if message.forward_from:
        tg_user_id = message.forward_from.id
    elif message.text:
        text = message.text.strip()
        if text.lstrip("@").isdigit() or text.isdigit():
            try:
                tg_user_id = int(text.lstrip("@"))
            except ValueError:
                pass
        elif text.startswith("@"):
            found = await get_user_by_username(text)
            if found:
                tg_user_id = found["user_id"]
            else:
                error_text = (
                    f"❌ Пользователь {text} не найден в базе бота.\n"
                    "Попросите мастера сначала запустить бота (/start), "
                    "затем попробуйте снова."
                )

    if error_text:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀️ Отмена", callback_data=f"adm:master:{master_id}"),
        ]])
        try:
            await bot.edit_message_caption(
                chat_id=message.chat.id, message_id=msg_id,
                caption=error_text, reply_markup=kb, parse_mode="HTML",
            )
        except Exception:
            try:
                await bot.edit_message_text(
                    chat_id=message.chat.id, message_id=msg_id,
                    text=error_text, reply_markup=kb, parse_mode="HTML",
                )
            except Exception:
                pass
        return

    if tg_user_id:
        await set_master_telegram_id(master_id, tg_user_id)

    await state.clear()
    m = await get_master(master_id)
    if m and msg_id:
        photo = m.get("photo_file_id") or SECTION_PHOTOS.get("masters")
        await edit_menu(
            bot, message.chat.id, msg_id,
            _master_card_text(m),
            _master_card_kb(master_id),
            photo_url=photo,
        )


# ── adm:master_add — добавить нового мастера ──────────────

@router.callback_query(F.data == "adm:master_add")
async def cb_adm_master_add(callback: CallbackQuery, state: FSMContext) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return
    await state.set_state(AdminStates.master_adding_name)
    await state.update_data(edit_msg_id=callback.message.message_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Отмена", callback_data="adm:masters"),
    ]])
    try:
        await callback.message.edit_caption(
            "➕ <b>Новый мастер</b>\n\nШаг 1/2: Введите имя мастера:",
            reply_markup=kb, parse_mode="HTML",
        )
    except Exception:
        await callback.message.edit_text(
            "➕ <b>Новый мастер</b>\n\nШаг 1/2: Введите имя мастера:",
            reply_markup=kb, parse_mode="HTML",
        )
    await callback.answer()


@router.message(AdminStates.master_adding_name)
async def msg_master_add_name(message: Message, bot: Bot, state: FSMContext) -> None:
    if not await is_admin(message.from_user.id):
        return
    name = message.text.strip() if message.text else ""
    try:
        await message.delete()
    except Exception:
        pass
    if not name:
        return
    data = await state.get_data()
    msg_id = data.get("edit_msg_id")
    await state.update_data(new_master_name=name)
    await state.set_state(AdminStates.master_adding_category)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💅 Маникюр",              callback_data="adm:master_add_cat:manicure")],
        [InlineKeyboardButton(text="✂️ Стрижка и окрашивание", callback_data="adm:master_add_cat:hair")],
        [InlineKeyboardButton(text="🪒 Барбершоп",             callback_data="adm:master_add_cat:barber")],
        [InlineKeyboardButton(text="◀️ Отмена",                callback_data="adm:masters")],
    ])
    try:
        await bot.edit_message_caption(
            chat_id=message.chat.id, message_id=msg_id,
            caption=f"➕ <b>Новый мастер: {name}</b>\n\nШаг 2/2: Выберите категорию:",
            reply_markup=kb, parse_mode="HTML",
        )
    except Exception:
        try:
            await bot.edit_message_text(
                chat_id=message.chat.id, message_id=msg_id,
                text=f"➕ <b>Новый мастер: {name}</b>\n\nШаг 2/2: Выберите категорию:",
                reply_markup=kb, parse_mode="HTML",
            )
        except Exception:
            pass


@router.callback_query(AdminStates.master_adding_category, F.data.startswith("adm:master_add_cat:"))
async def cb_adm_master_add_cat(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return
    category = callback.data[len("adm:master_add_cat:"):]
    data = await state.get_data()
    name = data.get("new_master_name", "Мастер")
    promote_user_id = data.get("promote_user_id")
    await state.clear()

    # Generate master_id from name
    import re as _re
    import time
    safe = _re.sub(r"[^a-z0-9]", "", name.lower().replace(" ", "_"))
    master_id = f"{safe[:10]}_{int(time.time()) % 10000}"

    await add_master_to_db(master_id, name, category)

    # Если назначение из профиля пользователя — привязываем TG
    if promote_user_id:
        await set_master_telegram_id(master_id, promote_user_id)
        # Уведомляем нового мастера
        try:
            await bot.send_message(
                chat_id=promote_user_id,
                text=(
                    f"🎉 <b>Поздравляем!</b>\n\n"
                    f"Вы назначены мастером в Studio ONE.\n"
                    f"Категория: <b>{_CAT_NAMES.get(category, category)}</b>\n\n"
                    f"Теперь при входе в бот вы увидите панель мастера.\n"
                    f"Там вы сможете просматривать записи и управлять расписанием.\n\n"
                    f"Отправьте /start чтобы открыть панель."
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning("Не удалось уведомить нового мастера %s: %s", promote_user_id, e)

    masters = await get_all_masters_admin()
    text = f"✅ <b>Мастер {name} добавлен!</b>\n\n" + await _build_masters_text(masters)
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        text, _masters_list_kb(masters),
        photo_url=SECTION_PHOTOS.get("masters"),
    )
    await callback.answer()


# ── adm:promote:{user_id} — назначить пользователя мастером ──

@router.callback_query(F.data.startswith("adm:promote:"))
async def cb_adm_promote_user(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return
    user_id = int(callback.data[len("adm:promote:"):])
    from database import get_user as _get_user
    u = await _get_user(user_id)
    if not u:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    name = u.get("full_name") or u.get("username") or str(user_id)
    await state.set_state(AdminStates.master_adding_category)
    await state.update_data(
        edit_msg_id=callback.message.message_id,
        new_master_name=name,
        promote_user_id=user_id,
        promote_user_name=name,
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💅 Маникюр",              callback_data="adm:master_add_cat:manicure")],
        [InlineKeyboardButton(text="✂️ Стрижка и окрашивание", callback_data="adm:master_add_cat:hair")],
        [InlineKeyboardButton(text="🪒 Барбершоп",             callback_data="adm:master_add_cat:barber")],
        [InlineKeyboardButton(text="◀️ Отмена",                callback_data=f"adm:user:{user_id}")],
    ])
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        f"👩‍🎨 <b>Назначить мастером: {name}</b>\n\nВыберите категорию:",
        kb, photo_url=SECTION_PHOTOS.get("masters"),
    )
    await callback.answer()


# ── FSM cancel handlers ────────────────────────────────────

@router.callback_query(
    AdminStates.master_editing_name, F.data.startswith("adm:master:")
)
@router.callback_query(
    AdminStates.master_editing_description, F.data.startswith("adm:master:")
)
@router.callback_query(
    AdminStates.master_editing_tg, F.data.startswith("adm:master:")
)
async def cb_cancel_master_edit(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    await state.clear()
    master_id = callback.data[len("adm:master:"):]
    m = await get_master(master_id)
    if m:
        photo = m.get("photo_file_id") or SECTION_PHOTOS.get("masters")
        await edit_menu(
            bot, callback.message.chat.id, callback.message.message_id,
            _master_card_text(m), _master_card_kb(master_id),
            photo_url=photo,
        )
    await callback.answer()


@router.callback_query(AdminStates.master_adding_name, F.data == "adm:masters")
@router.callback_query(AdminStates.master_adding_category, F.data == "adm:masters")
async def cb_cancel_master_add(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    await state.clear()
    masters = await get_all_masters_admin()
    text = await _build_masters_text(masters)
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        text, _masters_list_kb(masters),
        photo_url=SECTION_PHOTOS.get("masters"),
    )
    await callback.answer()
