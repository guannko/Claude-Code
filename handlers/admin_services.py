"""
Управление услугами и категориями через панель администратора.

callback_data:
  adm_svc:list          — список всех услуг (по категориям)
  adm_svc:cat:{key}     — услуги категории + управление
  adm_svc:edit:{sid}    — редактировать услугу
  adm_svc:toggle:{sid}  — вкл/выкл услугу
  adm_svc:del:{sid}     — удалить услугу
  adm_svc:add_form:{cat}— форма добавления услуги в категорию
  adm_svc:cats          — управление категориями
  adm_svc:cat_toggle:{key} — вкл/выкл категорию
"""

import logging
from aiogram import Router, Bot, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from database import (
    get_categories, get_category_by_key,
    get_db_services_by_category, get_db_service_by_id,
    get_all_services_admin,
    add_db_service, update_db_service, delete_db_service,
    update_db_category,
    get_user_lang,
    log_action,
)
from services.permissions import is_admin
from services.sender import edit_menu
from data.salon import SECTION_PHOTOS

logger = logging.getLogger(__name__)
router = Router()


class AdminServiceStates(StatesGroup):
    editing_field = State()    # редактируем поле (name/price/duration)
    adding_service = State()   # добавляем новую услугу (JSON-строка "имя|цена|длит")


# ── Вспомогательные ────────────────────────────────────────

def _back_to_list_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ К списку услуг", callback_data="adm_svc:list"),
    ]])


async def _services_list_text() -> str:
    import aiosqlite
    from config import DB_PATH
    lines = ["📋 <b>Услуги салона</b>\n"]
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM service_categories ORDER BY sort_order, cat_key"
        ) as cur:
            all_cats = [dict(r) for r in await cur.fetchall()]
        for cat in all_cats:
            status = "" if cat["is_active"] else " 🔴"
            lines.append(f"\n{cat['title']}{status}:")
            async with db.execute(
                "SELECT * FROM services WHERE category=? ORDER BY sort_order, id",
                (cat["cat_key"],)
            ) as cur:
                items = [dict(r) for r in await cur.fetchall()]
            if items:
                for item in items:
                    active = "✅" if item["is_active"] else "❌"
                    lines.append(f"  {active} {item['name']} — {item['price']}₽ / {item['duration']} мин")
            else:
                lines.append("  (нет услуг)")
    return "\n".join(lines)


def _services_mgmt_kb() -> InlineKeyboardMarkup:
    """Кнопки управления списком услуг."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редактировать услугу", callback_data="adm_svc:select_edit")],
        [InlineKeyboardButton(text="➕ Добавить услугу",      callback_data="adm_svc:select_add")],
        [InlineKeyboardButton(text="🗂 Категории",             callback_data="adm_svc:cats")],
        [InlineKeyboardButton(text="◀️ Назад",                callback_data="adm:panel")],
    ])


async def _cat_select_kb(action: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора категории для действия (add/edit)."""
    cats = await get_categories()
    buttons = []
    for cat in cats:
        buttons.append([InlineKeyboardButton(
            text=cat["title"],
            callback_data=f"adm_svc:{action}:{cat['cat_key']}",
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="adm_svc:list")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def _services_select_kb(category: str, action: str) -> InlineKeyboardMarkup:
    """Выбор конкретной услуги категории для редактирования."""
    import aiosqlite
    from config import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM services WHERE category=? ORDER BY sort_order, id",
            (category,)
        ) as cur:
            items = [dict(r) for r in await cur.fetchall()]

    buttons = []
    for item in items:
        active = "✅" if item["is_active"] else "❌"
        buttons.append([InlineKeyboardButton(
            text=f"{active} {item['name']} — {item['price']}₽",
            callback_data=f"adm_svc:{action}:{item['service_id']}",
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"adm_svc:select_{action.split('_')[0]}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _service_edit_kb(service_id: str) -> InlineKeyboardMarkup:
    """Кнопки редактирования конкретной услуги."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Название",   callback_data=f"adm_svc:field:name:{service_id}"),
            InlineKeyboardButton(text="💰 Цена",        callback_data=f"adm_svc:field:price:{service_id}"),
        ],
        [
            InlineKeyboardButton(text="⏱ Длительность", callback_data=f"adm_svc:field:duration:{service_id}"),
            InlineKeyboardButton(
                text="🔄 Вкл/Выкл",
                callback_data=f"adm_svc:toggle:{service_id}",
            ),
        ],
        [
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"adm_svc:del:{service_id}"),
        ],
        [InlineKeyboardButton(text="◀️ К списку", callback_data="adm_svc:list")],
    ])


# ── Главный список ─────────────────────────────────────────

@router.callback_query(F.data == "adm_svc:list")
async def cb_adm_svc_list(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    if not await is_admin(callback.from_user.id):
        return await callback.answer()
    await state.clear()
    text = await _services_list_text()
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        text, _services_mgmt_kb(),
        photo_url=SECTION_PHOTOS.get("services"),
    )
    await callback.answer()


# ── Выбор категории для добавления ────────────────────────

@router.callback_query(F.data == "adm_svc:select_add")
async def cb_adm_svc_select_add(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    if not await is_admin(callback.from_user.id):
        return await callback.answer()
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        "➕ <b>Выберите категорию для новой услуги:</b>",
        await _cat_select_kb("add_form"),
        photo_url=SECTION_PHOTOS.get("services"),
    )
    await callback.answer()


# ── Форма добавления услуги ────────────────────────────────

@router.callback_query(F.data.startswith("adm_svc:add_form:"))
async def cb_adm_svc_add_form(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    if not await is_admin(callback.from_user.id):
        return await callback.answer()
    category = callback.data.split(":", 2)[2]
    cat = await get_category_by_key(category)
    cat_title = cat["title"] if cat else category

    await state.set_state(AdminServiceStates.adding_service)
    await state.update_data(add_category=category, menu_msg_id=callback.message.message_id)

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Отмена", callback_data="adm_svc:list")
    ]])
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        f"➕ <b>Новая услуга в категорию «{cat_title}»</b>\n\n"
        "Введите данные в формате:\n"
        "<code>Название | цена | длительность_мин</code>\n\n"
        "Пример:\n<code>Маникюр классический | 900 | 45</code>",
        kb,
        photo_url=SECTION_PHOTOS.get("services"),
    )
    await callback.answer()


@router.message(AdminServiceStates.adding_service)
async def msg_adm_svc_add(message: Message, bot: Bot, state: FSMContext) -> None:
    if not await is_admin(message.from_user.id):
        return

    try:
        await message.delete()
    except Exception:
        pass

    raw = (message.text or "").strip()
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) != 3:
        await message.answer(
            "⚠️ Неверный формат. Введите: <b>Название | цена | длительность_мин</b>",
            parse_mode="HTML",
        )
        return

    name_str, price_str, dur_str = parts
    try:
        price = int(price_str)
        duration = int(dur_str)
    except ValueError:
        await message.answer("⚠️ Цена и длительность должны быть числами.", parse_mode="HTML")
        return

    data = await state.get_data()
    category = data.get("add_category", "")
    menu_msg_id = data.get("menu_msg_id")

    # Генерируем уникальный service_id
    import time
    service_id = f"svc_{int(time.time())}"

    try:
        await add_db_service(service_id, category, name_str, price, duration)
        await log_action(message.from_user.id, "service_add", target=service_id,
                         details=f"{name_str} | {price}₽ | {duration}мин | cat={category}")
    except Exception as e:
        await log_action(message.from_user.id, "service_add", target=service_id,
                         status="error", details=str(e))
        await message.answer(f"⚠️ Ошибка сохранения: {e}", parse_mode="HTML")
        return

    await state.clear()

    text = await _services_list_text()
    if menu_msg_id:
        try:
            await edit_menu(
                bot, message.chat.id, menu_msg_id,
                text, _services_mgmt_kb(),
                photo_url=SECTION_PHOTOS.get("services"),
            )
        except Exception:
            pass
    await message.answer(f"✅ Услуга <b>{name_str}</b> добавлена!", parse_mode="HTML")


# ── Выбор категории для редактирования ────────────────────

@router.callback_query(F.data == "adm_svc:select_edit")
async def cb_adm_svc_select_edit(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    if not await is_admin(callback.from_user.id):
        return await callback.answer()
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        "✏️ <b>Выберите категорию:</b>",
        await _cat_select_kb("cat_edit"),
        photo_url=SECTION_PHOTOS.get("services"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_svc:cat_edit:"))
async def cb_adm_svc_cat_edit(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    if not await is_admin(callback.from_user.id):
        return await callback.answer()
    category = callback.data.split(":", 2)[2]
    cat = await get_category_by_key(category)
    cat_title = cat["title"] if cat else category
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        f"✏️ <b>{cat_title}</b>\n\nВыберите услугу для редактирования:",
        await _services_select_kb(category, "edit_svc"),
        photo_url=SECTION_PHOTOS.get("services"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_svc:edit_svc:"))
async def cb_adm_svc_edit(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    if not await is_admin(callback.from_user.id):
        return await callback.answer()
    service_id = callback.data.split(":", 2)[2]
    svc = await get_db_service_by_id(service_id)
    if not svc:
        return await callback.answer("Услуга не найдена", show_alert=True)

    active = "✅ активна" if svc["is_active"] else "❌ отключена"
    text = (
        f"✏️ <b>{svc['name']}</b>\n\n"
        f"💰 Цена: {svc['price']}₽\n"
        f"⏱ Длительность: {svc['duration']} мин\n"
        f"Статус: {active}\n"
        f"ID: <code>{service_id}</code>"
    )
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        text, _service_edit_kb(service_id),
        photo_url=SECTION_PHOTOS.get("services"),
    )
    await callback.answer()


# ── Редактирование поля ────────────────────────────────────

@router.callback_query(F.data.startswith("adm_svc:field:"))
async def cb_adm_svc_field(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    if not await is_admin(callback.from_user.id):
        return await callback.answer()
    # adm_svc:field:{field}:{service_id}
    parts = callback.data.split(":", 3)
    field = parts[2]
    service_id = parts[3]
    svc = await get_db_service_by_id(service_id)
    if not svc:
        return await callback.answer("Услуга не найдена", show_alert=True)

    field_labels = {"name": "название", "price": "цену (число)", "duration": "длительность в минутах (число)"}
    current = svc.get(field, "")

    await state.set_state(AdminServiceStates.editing_field)
    await state.update_data(edit_service_id=service_id, edit_field=field, menu_msg_id=callback.message.message_id)

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Отмена", callback_data=f"adm_svc:edit_svc:{service_id}")
    ]])
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        f"✏️ <b>{svc['name']}</b>\n\n"
        f"Введите новое {field_labels.get(field, field)}:\n"
        f"Текущее значение: <code>{current}</code>",
        kb,
        photo_url=SECTION_PHOTOS.get("services"),
    )
    await callback.answer()


@router.message(AdminServiceStates.editing_field)
async def msg_adm_svc_field(message: Message, bot: Bot, state: FSMContext) -> None:
    if not await is_admin(message.from_user.id):
        return

    try:
        await message.delete()
    except Exception:
        pass

    data = await state.get_data()
    service_id = data.get("edit_service_id")
    field = data.get("edit_field")
    menu_msg_id = data.get("menu_msg_id")

    new_value = (message.text or "").strip()

    # Валидация числовых полей
    if field in ("price", "duration"):
        try:
            new_value = int(new_value)
        except ValueError:
            await message.answer(f"⚠️ Введите целое число.", parse_mode="HTML")
            return

    await update_db_service(service_id, **{field: new_value})
    await log_action(message.from_user.id, "service_edit", target=service_id,
                     details=f"field={field} → {new_value}")
    await state.clear()

    svc = await get_db_service_by_id(service_id)
    if svc and menu_msg_id:
        active = "✅ активна" if svc["is_active"] else "❌ отключена"
        text = (
            f"✏️ <b>{svc['name']}</b>\n\n"
            f"💰 Цена: {svc['price']}₽\n"
            f"⏱ Длительность: {svc['duration']} мин\n"
            f"Статус: {active}\n"
            f"ID: <code>{service_id}</code>\n\n"
            f"✅ Сохранено!"
        )
        try:
            await edit_menu(
                bot, message.chat.id, menu_msg_id,
                text, _service_edit_kb(service_id),
                photo_url=SECTION_PHOTOS.get("services"),
            )
        except Exception:
            pass


# ── Вкл/Выкл услуги ───────────────────────────────────────

@router.callback_query(F.data.startswith("adm_svc:toggle:"))
async def cb_adm_svc_toggle(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    if not await is_admin(callback.from_user.id):
        return await callback.answer()
    service_id = callback.data.split(":", 2)[2]
    svc = await get_db_service_by_id(service_id)
    if not svc:
        return await callback.answer("Услуга не найдена", show_alert=True)

    new_active = 0 if svc["is_active"] else 1
    await update_db_service(service_id, is_active=new_active)
    await log_action(callback.from_user.id, "service_toggle", target=service_id,
                     details=f"active → {new_active}")

    svc = await get_db_service_by_id(service_id)
    active = "✅ активна" if svc["is_active"] else "❌ отключена"
    text = (
        f"✏️ <b>{svc['name']}</b>\n\n"
        f"💰 Цена: {svc['price']}₽\n"
        f"⏱ Длительность: {svc['duration']} мин\n"
        f"Статус: {active}\n"
        f"ID: <code>{service_id}</code>"
    )
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        text, _service_edit_kb(service_id),
        photo_url=SECTION_PHOTOS.get("services"),
    )
    await callback.answer("✅ Статус изменён")


# ── Удаление услуги ────────────────────────────────────────

@router.callback_query(F.data.startswith("adm_svc:del:"))
async def cb_adm_svc_del(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    if not await is_admin(callback.from_user.id):
        return await callback.answer()
    service_id = callback.data.split(":", 2)[2]
    svc = await get_db_service_by_id(service_id)
    if not svc:
        return await callback.answer("Услуга не найдена", show_alert=True)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚠️ Да, удалить", callback_data=f"adm_svc:del_confirm:{service_id}"),
            InlineKeyboardButton(text="◀️ Отмена",      callback_data=f"adm_svc:edit_svc:{service_id}"),
        ]
    ])
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        f"🗑 Удалить услугу <b>{svc['name']}</b>?\n\nЭто действие необратимо.",
        kb,
        photo_url=SECTION_PHOTOS.get("services"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_svc:del_confirm:"))
async def cb_adm_svc_del_confirm(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    if not await is_admin(callback.from_user.id):
        return await callback.answer()
    service_id = callback.data.split(":", 2)[2]
    svc_to_del = await get_db_service_by_id(service_id)
    await delete_db_service(service_id)
    await log_action(callback.from_user.id, "service_delete", target=service_id,
                     details=svc_to_del["name"] if svc_to_del else "")
    text = await _services_list_text()
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        text + "\n\n✅ Услуга удалена.",
        _services_mgmt_kb(),
        photo_url=SECTION_PHOTOS.get("services"),
    )
    await callback.answer("🗑 Удалено")


# ── Управление категориями ─────────────────────────────────

@router.callback_query(F.data == "adm_svc:cats")
async def cb_adm_svc_cats(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    if not await is_admin(callback.from_user.id):
        return await callback.answer()

    import aiosqlite
    from config import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM service_categories ORDER BY sort_order, cat_key"
        ) as cur:
            all_cats = [dict(r) for r in await cur.fetchall()]

    lines = ["🗂 <b>Категории услуг</b>\n"]
    for cat in all_cats:
        status = "✅" if cat["is_active"] else "❌"
        lines.append(f"{status} {cat['title']} (<code>{cat['cat_key']}</code>)")

    buttons = []
    for cat in all_cats:
        status = "🔴 Выкл" if cat["is_active"] else "🟢 Вкл"
        buttons.append([InlineKeyboardButton(
            text=f"{status}: {cat['title']}",
            callback_data=f"adm_svc:cat_toggle:{cat['cat_key']}",
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="adm_svc:list")])

    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        "\n".join(lines),
        InlineKeyboardMarkup(inline_keyboard=buttons),
        photo_url=SECTION_PHOTOS.get("services"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_svc:cat_toggle:"))
async def cb_adm_svc_cat_toggle(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    if not await is_admin(callback.from_user.id):
        return await callback.answer()
    cat_key = callback.data.split(":", 2)[2]
    cat = await get_category_by_key(cat_key)
    if not cat:
        return await callback.answer("Категория не найдена", show_alert=True)
    new_active = 0 if cat["is_active"] else 1
    await update_db_category(cat_key, is_active=new_active)
    await log_action(callback.from_user.id, "category_toggle", target=cat_key,
                     details=f"active → {new_active}")

    # Обновляем экран категорий
    import aiosqlite
    from config import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM service_categories ORDER BY sort_order, cat_key"
        ) as cur:
            all_cats = [dict(r) for r in await cur.fetchall()]

    lines = ["🗂 <b>Категории услуг</b>\n"]
    for c in all_cats:
        status = "✅" if c["is_active"] else "❌"
        lines.append(f"{status} {c['title']} (<code>{c['cat_key']}</code>)")

    buttons = []
    for c in all_cats:
        status = "🔴 Выкл" if c["is_active"] else "🟢 Вкл"
        buttons.append([InlineKeyboardButton(
            text=f"{status}: {c['title']}",
            callback_data=f"adm_svc:cat_toggle:{c['cat_key']}",
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="adm_svc:list")])

    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        "\n".join(lines),
        InlineKeyboardMarkup(inline_keyboard=buttons),
        photo_url=SECTION_PHOTOS.get("services"),
    )
    await callback.answer("✅ Статус категории изменён")
