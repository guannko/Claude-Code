"""
Флоу записи через выбор мастера + система подтверждения.

Callback-схема:
  mst:cats                                     — выбор категории
  mst:cat:{category}                           — список мастеров категории
  mst:pick:{master_id}                         — выбор услуги у мастера
  mst:svc:{master_id}:{service_id}             — показать даты
  mst:date:{master_id}:{service_id}:{date}     — показать слоты
  mst:slot:{master_id}:{service_id}:{date}:{time} — запросить телефон (FSM)
  mst:confirm:{master_id}:{service_id}:{date}:{time} — создать запись
  mst:cancel                                   — отмена
  mst:approve:{booking_id}:{client_user_id}    — мастер принял
  mst:reject:{booking_id}:{client_user_id}     — мастер отклонил
"""

import logging
from datetime import date as date_cls

from aiogram import Router, Bot, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from config import ADMIN_ID
from services.permissions import is_admin
from database import (
    create_booking,
    get_masters_by_category,
    get_master,
    update_booking_status,
    get_user_lang,
    get_user_phone,
    update_user_phone,
    get_user,
    save_last_msg_id,
)
from keyboards import (
    main_menu_kb,
    master_categories_kb,
    masters_list_kb,
    master_services_kb,
    master_dates_kb,
    master_slots_kb,
    master_confirm_kb,
    master_response_kb,
)
from services.sender import edit_menu
from states import MasterFlowStates
from data.salon import SECTION_PHOTOS
from database import get_categories, get_category_by_key, get_db_services_by_category, get_db_service_by_id, get_setting

logger = logging.getLogger(__name__)
router = Router()

# Русские названия для форматирования дат
_DAYS_RU = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
_MONTHS_GEN_RU = [
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]

# Иконки категорий
_CAT_ICONS = {
    "manicure": "💅",
    "hair": "✂️",
    "barber": "🪒",
}


def _fmt_date(d: date_cls) -> str:
    """Возвращает строку вида 'Пятница, 4 апреля'."""
    return f"{_DAYS_RU[d.weekday()]}, {d.day} {_MONTHS_GEN_RU[d.month]}"


def _fmt_duration(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} мин"
    hours = minutes / 60
    if hours == int(hours):
        return f"{int(hours)} ч"
    return f"{hours} ч"


async def _get_service_by_id(service_id: str) -> dict | None:
    return await get_db_service_by_id(service_id)


async def _get_services_for_category(category: str) -> list[dict]:
    return await get_db_services_by_category(category)


def _cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="mst:cancel")]
    ])


# ── mst:cats — выбор категории ────────────────────────────

@router.callback_query(F.data == "mst:cats")
async def cb_mst_cats(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    await state.clear()
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        "👩‍🎨 <b>Выберите категорию мастера:</b>",
        await master_categories_kb(),
        photo_url=SECTION_PHOTOS.get("masters"),
    )
    await callback.answer()


# ── mst:cat:{category} — список мастеров ─────────────────

@router.callback_query(F.data.startswith("mst:cat:"))
async def cb_mst_cat(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    category = callback.data[len("mst:cat:"):]
    masters = await get_masters_by_category(category)

    if not masters:
        await callback.answer("Мастера не найдены", show_alert=True)
        return

    icon = _CAT_ICONS.get(category, "👩‍🎨")
    cat = await get_category_by_key(category) or {}
    cat_title = cat.get("title", category)

    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        f"{icon} <b>{cat_title}</b>\n\nВыберите мастера:",
        masters_list_kb(masters),
        photo_url=SECTION_PHOTOS.get("masters"),
    )
    await callback.answer()


# ── mst:pick:{master_id} — список услуг мастера ──────────

@router.callback_query(F.data.startswith("mst:pick:"))
async def cb_mst_pick(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    master_id = callback.data[len("mst:pick:"):]
    master = await get_master(master_id)

    if not master:
        await callback.answer("Мастер не найден", show_alert=True)
        return

    services = await _get_services_for_category(master["category"])
    if not services:
        await callback.answer("Услуги не найдены", show_alert=True)
        return

    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        f"👤 <b>Мастер: {master['name']}</b>\n\nВыберите услугу:",
        master_services_kb(master_id, services),
        photo_url=SECTION_PHOTOS.get("masters"),
    )
    await callback.answer()


# ── mst:svc:{master_id}:{service_id} — показать даты ─────

@router.callback_query(F.data.startswith("mst:svc:"))
async def cb_mst_svc(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    from services.slots import get_available_dates

    # mst:svc:{master_id}:{service_id}
    rest = callback.data[len("mst:svc:"):]
    # service_id может содержать "_", master_id тоже — разбиваем по первому ":"
    colon_idx = rest.index(":")
    master_id = rest[:colon_idx]
    service_id = rest[colon_idx + 1:]

    master = await get_master(master_id)
    service = await _get_service_by_id(service_id)

    if not master or not service:
        await callback.answer("Данные не найдены", show_alert=True)
        return

    available_dates = await get_available_dates(master_id)

    if not available_dates:
        await callback.answer(
            "К сожалению, в ближайшие 14 дней нет свободных дат. "
            f"Позвоните нам: {await get_setting('salon_phone', '+7 (495) 123-45-67')}",
            show_alert=True,
        )
        return

    await state.update_data(
        master_id=master_id,
        master_name=master["name"],
        service_id=service_id,
        service_name=service["name"],
        service_price=service["price"],
        service_duration=service["duration"],
        menu_msg_id=callback.message.message_id,
    )

    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        f"👤 <b>Мастер:</b> {master['name']}\n"
        f"💅 <b>Услуга:</b> {service['name']} — {service['price']}₽\n\n"
        f"📅 <b>Выберите дату:</b>",
        master_dates_kb(available_dates, master_id, service_id),
        photo_url=SECTION_PHOTOS.get("booking"),
    )
    await callback.answer()


# ── mst:date:{master_id}:{service_id}:{date} — показать слоты

@router.callback_query(F.data.startswith("mst:date:"))
async def cb_mst_date(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    from services.slots import get_free_slots

    # mst:date:{master_id}:{service_id}:{YYYY-MM-DD}
    rest = callback.data[len("mst:date:"):]
    parts = rest.split(":")
    # parts = [master_id, service_id, "YYYY-MM-DD"]
    master_id = parts[0]
    service_id = parts[1]
    date_str = parts[2]

    data = await state.get_data()
    duration = data.get("service_duration", 60)

    try:
        target_date = date_cls.fromisoformat(date_str)
    except ValueError:
        await callback.answer("Неверная дата", show_alert=True)
        return

    free_slots = await get_free_slots(master_id, target_date, duration)

    if not free_slots:
        await callback.answer(
            "На эту дату нет свободных слотов. Выбери другую дату.",
            show_alert=True,
        )
        return

    _m_rec = await get_master(master_id)
    master_name = data.get("master_name") or (_m_rec["name"] if _m_rec else master_id)
    service_name = data.get("service_name", "")
    date_label = _fmt_date(target_date)

    await state.update_data(date=date_str)

    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        f"👤 <b>Мастер:</b> {master_name}\n"
        f"💅 <b>Услуга:</b> {service_name}\n"
        f"📅 <b>Дата:</b> {date_label}\n\n"
        f"⏰ <b>Выберите время:</b>",
        master_slots_kb(free_slots, master_id, service_id, date_str),
        photo_url=SECTION_PHOTOS.get("booking"),
    )
    await callback.answer()


# ── mst:slot:... — запросить телефон (FSM) ────────────────

@router.callback_query(F.data.startswith("mst:slot:"))
async def cb_mst_slot(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    # mst:slot:{master_id}:{service_id}:{YYYY-MM-DD}:{HH:MM}
    rest = callback.data[len("mst:slot:"):]
    parts = rest.split(":")
    # parts = [master_id, service_id, "YYYY-MM-DD", "HH", "MM"]
    master_id = parts[0]
    service_id = parts[1]
    date_str = parts[2]
    time_str = f"{parts[3]}:{parts[4]}"

    await state.update_data(
        master_id=master_id,
        service_id=service_id,
        date=date_str,
        time_start=time_str,
        menu_msg_id=callback.message.message_id,
    )

    stored_phone = await get_user_phone(callback.from_user.id)

    if stored_phone:
        # Телефон уже есть — спрашиваем подтверждение
        await state.update_data(phone=stored_phone)
        await state.set_state(MasterFlowStates.confirming_phone)

        phone_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text=f"✅ Да, {stored_phone}", callback_data="mst:use_phone"),
                InlineKeyboardButton(text="✏️ Изменить номер",       callback_data="mst:change_phone"),
            ],
        ])
        await edit_menu(
            bot, callback.message.chat.id, callback.message.message_id,
            f"📞 <b>Использовать сохранённый номер?</b>\n\n<code>{stored_phone}</code>",
            phone_kb,
            photo_url=SECTION_PHOTOS.get("booking"),
        )
    else:
        await state.set_state(MasterFlowStates.waiting_phone)
        await edit_menu(
            bot, callback.message.chat.id, callback.message.message_id,
            "📞 <b>Введите ваш номер телефона:</b>\n\nНапример: +7 999 123-45-67",
            _cancel_kb(),
            photo_url=SECTION_PHOTOS.get("booking"),
        )
    await callback.answer()


@router.callback_query(MasterFlowStates.confirming_phone, F.data == "mst:use_phone")
async def cb_mst_use_stored_phone(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    """Клиент подтвердил использование сохранённого номера в мастер-флоу."""
    data = await state.get_data()
    phone = data.get("phone", "—")
    msg_id = data.get("menu_msg_id")
    master_id = data.get("master_id", "")
    service_id = data.get("service_id", "")
    date_str = data.get("date", "")
    time_str = data.get("time_start", "")
    duration = data.get("service_duration", 0)

    try:
        target_date = date_cls.fromisoformat(date_str)
        date_formatted = _fmt_date(target_date)
    except (ValueError, TypeError):
        date_formatted = date_str

    dur_str = _fmt_duration(duration)

    confirm_text = (
        "✅ <b>Подтвердите запись</b>\n\n"
        f"💅 <b>Услуга:</b> {data.get('service_name', '—')} — {data.get('service_price', '—')}₽\n"
        f"👤 <b>Мастер:</b> {data.get('master_name', '—')}\n"
        f"📅 <b>Дата:</b> {date_formatted}\n"
        f"⏰ <b>Время:</b> {time_str}\n"
        f"⏱ <b>Длительность:</b> {dur_str}\n"
        f"📞 <b>Телефон:</b> {phone}\n\n"
        "Нажмите ✅ для подтверждения"
    )

    kb = master_confirm_kb(master_id, service_id, date_str, time_str)

    await edit_menu(
        bot, callback.message.chat.id, msg_id,
        confirm_text, kb,
        photo_url=SECTION_PHOTOS.get("booking"),
    )
    await callback.answer()


@router.callback_query(MasterFlowStates.confirming_phone, F.data == "mst:change_phone")
async def cb_mst_change_phone(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    """Клиент хочет ввести другой номер в мастер-флоу."""
    await state.set_state(MasterFlowStates.waiting_phone)
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        "📞 <b>Введите ваш номер телефона:</b>\n\nНапример: +7 999 123-45-67",
        _cancel_kb(),
        photo_url=SECTION_PHOTOS.get("booking"),
    )
    await callback.answer()


# ── Получили телефон — показываем карточку подтверждения ─

@router.message(MasterFlowStates.waiting_phone)
async def msg_mst_phone(message: Message, bot: Bot, state: FSMContext) -> None:
    phone = message.text.strip()
    await state.update_data(phone=phone)
    await update_user_phone(message.from_user.id, phone)

    try:
        await message.delete()
    except Exception:
        pass

    data = await state.get_data()
    msg_id = data.get("menu_msg_id")
    date_str = data.get("date", "")
    time_str = data.get("time_start", "")
    duration = data.get("service_duration", 0)
    master_id = data.get("master_id", "")
    service_id = data.get("service_id", "")

    try:
        target_date = date_cls.fromisoformat(date_str)
        date_formatted = _fmt_date(target_date)
    except (ValueError, TypeError):
        date_formatted = date_str

    dur_str = _fmt_duration(duration)

    confirm_text = (
        "✅ <b>Подтвердите запись</b>\n\n"
        f"💅 <b>Услуга:</b> {data.get('service_name', '—')} — {data.get('service_price', '—')}₽\n"
        f"👤 <b>Мастер:</b> {data.get('master_name', '—')}\n"
        f"📅 <b>Дата:</b> {date_formatted}\n"
        f"⏰ <b>Время:</b> {time_str}\n"
        f"⏱ <b>Длительность:</b> {dur_str}\n"
        f"📞 <b>Телефон:</b> {phone}\n\n"
        "Нажмите ✅ для подтверждения"
    )

    kb = master_confirm_kb(master_id, service_id, date_str, time_str)

    await edit_menu(
        bot, message.chat.id, msg_id,
        confirm_text, kb,
        photo_url=SECTION_PHOTOS.get("booking"),
    )


# ── mst:confirm:... — создать запись и уведомить мастера ─

@router.callback_query(F.data.startswith("mst:confirm:"))
async def cb_mst_confirm(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    # mst:confirm:{master_id}:{service_id}:{YYYY-MM-DD}:{HH:MM}
    rest = callback.data[len("mst:confirm:"):]
    parts = rest.split(":")
    master_id = parts[0]
    service_id = parts[1]
    date_str = parts[2]
    time_str = f"{parts[3]}:{parts[4]}"

    data = await state.get_data()
    user = callback.from_user
    username_str = f"@{user.username}" if user.username else "без username"
    # Берём имя из нашей БД (то, что клиент ввёл при регистрации)
    user_db = await get_user(user.id)
    client_name = (user_db or {}).get("full_name") or user.full_name or user.first_name or str(user.id)
    phone = data.get("phone", "—")
    service_name = data.get("service_name", "—")
    service_price = data.get("service_price", "—")
    master_name = data.get("master_name", "—")
    duration = data.get("service_duration", 0)

    try:
        target_date = date_cls.fromisoformat(date_str)
        date_formatted = _fmt_date(target_date)
    except (ValueError, TypeError):
        date_formatted = date_str

    dur_str = _fmt_duration(duration)

    # Создать запись со статусом pending_master (атомарная проверка на race condition)
    booking_id = await create_booking(
        user_id=user.id,
        user_name=client_name,
        username=username_str,
        service=service_name,
        service_id=service_id,
        master=master_name,
        master_id=master_id,
        date=date_str,
        time_start=time_str,
        duration=duration,
        phone=phone,
    )
    if booking_id is None:
        # Слот уже занят — другой клиент успел раньше
        await state.clear()
        await edit_menu(
            bot, callback.message.chat.id, callback.message.message_id,
            "⚠️ <b>Упс, этот слот только что заняли!</b>\n\n"
            "Пожалуйста, выберите другое время.",
            InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔄 Выбрать другое время",
                                     callback_data=f"mst:master:{master_id}")
            ]]),
            photo_url=SECTION_PHOTOS.get("booking"),
        )
        await callback.answer("Слот занят, выберите другое время.", show_alert=True)
        return
    await update_booking_status(booking_id, "pending_master")

    # Лояльность: увеличить счётчик посещений
    try:
        from database import increment_visit_count
        visit_count = await increment_visit_count(user.id)
        if visit_count % 5 == 0:
            await bot.send_message(
                chat_id=user.id,
                text=(
                    f"🎉 <b>Поздравляем с {visit_count}-м визитом!</b>\n\n"
                    "В знак благодарности за вашу верность дарим вам "
                    "<b>скидку 10%</b> на следующую услугу.\n\n"
                    "Просто покажите это сообщение при записи 😊"
                ),
                parse_mode="HTML",
            )
    except Exception as e:
        logger.warning("Лояльность: ошибка: %s", e)

    await state.clear()

    # Сообщение клиенту — ожидание подтверждения
    client_text = (
        f"⏳ <b>Запись отправлена мастеру!</b>\n\n"
        f"Ждём подтверждения от {master_name}.\n"
        f"Обычно мастера отвечают в течение 1 часа.\n\n"
        f"Если срочно — позвоните: {await get_setting('salon_phone', '+7 (495) 123-45-67')}"
    )
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        client_text,
        InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main")]
        ]),
        photo_url=SECTION_PHOTOS.get("booking"),
    )
    # Явно обновляем last_msg_id — чтобы /start корректно отредактировал это сообщение
    await save_last_msg_id(callback.from_user.id, callback.message.message_id)
    await callback.answer("✅ Запись отправлена!")

    # Определяем кому отправить уведомление: мастеру или админу
    master_db = await get_master(master_id)
    notify_id = None
    if master_db and master_db.get("telegram_user_id"):
        notify_id = master_db["telegram_user_id"]
    elif ADMIN_ID:
        notify_id = ADMIN_ID

    if not notify_id:
        logger.warning("Нет получателя для уведомления о записи #%s", booking_id)
        return

    notify_text = (
        f"🔔 <b>Новая запись на подтверждение!</b>\n\n"
        f"💅 <b>Услуга:</b> {service_name}\n"
        f"👤 <b>Клиент:</b> {client_name}\n"
        f"📅 <b>Дата:</b> {date_formatted}\n"
        f"⏰ <b>Время:</b> {time_str}\n"
        f"⏱ <b>Длительность:</b> {dur_str}\n"
        f"📞 <b>Телефон:</b> {phone}\n"
        f"🆔 <b>Запись #{booking_id}</b>"
    )

    try:
        await bot.send_message(
            chat_id=notify_id,
            text=notify_text,
            reply_markup=master_response_kb(booking_id, user.id),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning("Не удалось отправить уведомление мастеру/админу: %s", e)


# ── mst:cancel — отмена, возврат в меню ──────────────────

@router.callback_query(F.data == "mst:cancel")
async def cb_mst_cancel(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    await state.clear()
    lang = await get_user_lang(callback.from_user.id)
    from texts import t
    from database import get_setting
    salon_name = await get_setting("salon_name", "Салон красоты")
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        t("main_menu_text", lang, name=callback.from_user.first_name, salon_name=salon_name),
        main_menu_kb(lang),
        photo_url=SECTION_PHOTOS.get("main"),
    )
    await callback.answer()


# ── mst:approve:{booking_id}:{client_user_id} ─────────────

@router.callback_query(F.data.startswith("mst:approve:"))
async def cb_mst_approve(callback: CallbackQuery, bot: Bot) -> None:
    from database import get_master_by_telegram_id as _get_master_by_tid
    # Разрешено: мастер (привязан telegram_user_id) или администратор
    caller_master = None
    try:
        caller_master = await _get_master_by_tid(callback.from_user.id)
    except Exception:
        pass
    if not caller_master and not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return
    rest = callback.data[len("mst:approve:"):]
    parts = rest.split(":")
    booking_id = int(parts[0])
    client_user_id = int(parts[1])

    await update_booking_status(booking_id, "confirmed")

    # Редактировать сообщение мастеру
    try:
        original = callback.message.text or ""
        await callback.message.edit_text(
            original + f"\n\n✅ <b>Запись #{booking_id} принята</b>",
            reply_markup=None,
            parse_mode="HTML",
        )
    except Exception:
        pass

    await callback.answer("✅ Запись принята")

    # Уведомить клиента
    # Попробуем получить детали из текста уведомления
    msg_text = callback.message.text or ""
    service_line = ""
    master_line = ""
    date_line = ""
    time_line = ""
    for line in msg_text.splitlines():
        stripped = line.strip()
        if "Услуга:" in stripped:
            service_line = stripped.split("Услуга:")[-1].strip()
        elif "Дата:" in stripped:
            date_line = stripped.split("Дата:")[-1].strip()
        elif "Время:" in stripped:
            time_line = stripped.split("Время:")[-1].strip()

    # Имя мастера берём из сообщения — ищем в БД по telegram_user_id
    master_name = "мастер"
    master_db = None
    from database import get_master_by_telegram_id
    try:
        master_db = await get_master_by_telegram_id(callback.from_user.id)
    except Exception:
        pass
    if master_db:
        master_name = master_db["name"]

    salon_address = await get_setting("salon_address", "")
    salon_metro = await get_setting("salon_metro", "")
    location_str = f"{salon_address} ({salon_metro})" if salon_metro else salon_address
    client_text = (
        f"✅ <b>Ваша запись подтверждена!</b>\n\n"
        f"💅 {service_line or '—'}\n"
        f"👤 Мастер: {master_name}\n"
        f"📅 {date_line} в {time_line}\n"
        f"📍 {location_str}\n\n"
        f"Ждём вас! 💇‍♀️"
    )

    confirmed_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 Записаться ещё", callback_data="mst:cats"),
            InlineKeyboardButton(text="🏠 В меню",         callback_data="notify:dismiss"),
        ]
    ])
    try:
        await bot.send_message(
            chat_id=client_user_id,
            text=client_text,
            reply_markup=confirmed_kb,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning("Не удалось отправить подтверждение клиенту %s: %s", client_user_id, e)


# ── mst:reject:{booking_id}:{client_user_id} ──────────────

@router.callback_query(F.data.startswith("mst:reject:"))
async def cb_mst_reject(callback: CallbackQuery, bot: Bot) -> None:
    from database import get_master_by_telegram_id as _get_master_by_tid2
    # Разрешено: мастер (привязан telegram_user_id) или администратор
    caller_master2 = None
    try:
        caller_master2 = await _get_master_by_tid2(callback.from_user.id)
    except Exception:
        pass
    if not caller_master2 and not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return
    rest = callback.data[len("mst:reject:"):]
    parts = rest.split(":")
    booking_id = int(parts[0])
    client_user_id = int(parts[1])

    await update_booking_status(booking_id, "rejected")

    # Редактировать сообщение мастеру
    try:
        original = callback.message.text or ""
        await callback.message.edit_text(
            original + f"\n\n❌ <b>Запись #{booking_id} отклонена</b>",
            reply_markup=None,
            parse_mode="HTML",
        )
    except Exception:
        pass

    await callback.answer("❌ Запись отклонена")

    # Уведомить клиента
    retry_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Записаться снова", callback_data="mst:cats"),
            InlineKeyboardButton(text="🏠 В меню",           callback_data="notify:dismiss"),
        ]
    ])
    client_text = (
        "😔 <b>К сожалению, мастер не сможет вас принять</b>\n\n"
        "Выберите другое время или другого мастера."
    )

    try:
        await bot.send_message(
            chat_id=client_user_id,
            text=client_text,
            reply_markup=retry_kb,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning("Не удалось отправить отказ клиенту %s: %s", client_user_id, e)
