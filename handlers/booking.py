"""
FSM-сценарий записи на приём (с реальными слотами).

Сценарий:
1. book:start            → выбор категории
2. services:cat:{cat}    → выбор услуги из категории
3. services:item:{id}    → сохраняем услугу, показываем мастеров
4. book:master:{id|any}  → показываем доступные даты
5. book:date:{m}:{date}  → показываем свободные слоты времени
6. book:slot:{m}:{d}:{t} → запрашиваем телефон (FSM waiting_phone)
7. Телефон → подтверждение (инлайн) → create_booking → уведомление
8. book:back:master      → назад к выбору мастера
   book:back:date:{m}    → назад к выбору даты
"""

import logging
from datetime import date as date_type
from aiogram import Router, Bot, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import ADMIN_ID
from database import (
    create_booking, get_user_lang, update_booking_status, get_booking,
    get_user_phone, update_user_phone, get_user, save_last_msg_id,
    get_db_service_by_id, get_db_services_by_category,
    get_category_by_key, get_masters_by_category, get_master,
)
from services.permissions import is_admin
from keyboards import (
    main_menu_kb, categories_kb, services_list_kb,
    confirm_booking_kb, after_booking_kb,
    admin_booking_kb, dates_kb, slots_kb,
)
from services.sender import edit_menu
from states import BookingStates
from texts import t
from data.salon import SECTION_PHOTOS

logger = logging.getLogger(__name__)
router = Router()

# Русские названия для форматирования дат
_DAYS_RU = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
_MONTHS_GEN_RU = [
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


# ── Вспомогательные функции ────────────────────────────────

def _fmt_date(d: date_type) -> str:
    """Возвращает строку вида 'Пятница, 4 апреля'."""
    return f"{_DAYS_RU[d.weekday()]}, {d.day} {_MONTHS_GEN_RU[d.month]}"


def _cancel_kb():
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="booking:cancel")]
    ])


# ── Шаг 1: старт — выбор категории ────────────────────────

@router.callback_query(F.data == "book:start")
async def cb_book_start(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(BookingStates.choosing_category)
    await state.update_data(menu_msg_id=callback.message.message_id)
    lang = await get_user_lang(callback.from_user.id)
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        t("booking_choose_category", lang),
        await categories_kb(),
        photo_url=SECTION_PHOTOS.get("booking"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("book:start:"))
async def cb_book_start_with_category(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    """Запись из просмотра категории: сначала выбор мастера, потом услуга."""
    category = callback.data.split(":")[2]
    await state.clear()
    await state.set_state(BookingStates.choosing_master)
    # from_category_start=True → после выбора мастера покажем услуги (не даты)
    await state.update_data(
        category=category,
        menu_msg_id=callback.message.message_id,
        from_category_start=True,
    )

    lang = await get_user_lang(callback.from_user.id)
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        t("booking_choose_master", lang),
        await _masters_with_schedule_kb(category, back_cb=f"services:cat:{category}"),
        photo_url=SECTION_PHOTOS.get(category, SECTION_PHOTOS.get("booking")),
    )
    await callback.answer()


# ── Шаг 2: выбрана категория — список услуг ───────────────

@router.callback_query(BookingStates.choosing_category, F.data.startswith("services:cat:"))
async def cb_book_choose_category(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    category = callback.data.split(":")[2]
    await state.update_data(category=category)
    await state.set_state(BookingStates.choosing_service)

    cat = await get_category_by_key(category) or {}
    lang = await get_user_lang(callback.from_user.id)
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        f"{cat.get('title', 'Услуги')}\n\n{t('booking_choose_service', lang)}",
        await services_list_kb(category),
        photo_url=SECTION_PHOTOS.get(category, SECTION_PHOTOS.get("booking")),
    )
    await callback.answer()


# ── Шаг 3: выбрана услуга — выбор мастера ─────────────────

@router.callback_query(BookingStates.choosing_service, F.data.startswith("services:item:"))
async def cb_book_choose_service(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    from services.slots import get_available_dates

    service_id = callback.data.split(":")[2]
    service = await get_db_service_by_id(service_id)
    if not service:
        await callback.answer("Услуга не найдена", show_alert=True)
        return

    category = service["category"]
    await state.update_data(
        service_id=service_id,
        service_name=service["name"],
        service_price=service["price"],
        service_duration=service["duration"],
        category=category,
    )
    data = await state.get_data()

    # Если мастер уже выбран (флоу: мастер → услуга → дата) — сразу к датам
    master_id = data.get("master_id")
    if master_id and data.get("from_category_start"):
        master_name = data.get("master_name", "")
        available_dates = await get_available_dates(master_id)
        if not available_dates:
            salon_phone = await _get_salon_phone()
            await callback.answer(
                f"К сожалению, нет свободных дат. Позвоните нам: {salon_phone}",
                show_alert=True,
            )
            return
        await state.set_state(BookingStates.choosing_master)
        await edit_menu(
            bot, callback.message.chat.id, callback.message.message_id,
            f"👤 <b>Мастер:</b> {master_name}\n"
            f"💅 <b>Услуга:</b> {service['name']} — {service['price']}₽\n\n"
            f"📅 <b>Выбери дату:</b>",
            dates_kb(available_dates, master_id),
            photo_url=SECTION_PHOTOS.get("booking"),
        )
        await callback.answer()
        return

    # Стандартный флоу: услуга → выбор мастера
    await state.set_state(BookingStates.choosing_master)
    lang = await get_user_lang(callback.from_user.id)
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        f"💅 <b>{service['name']}</b> — {service['price']}₽\n\n"
        f"{t('booking_choose_master', lang)}",
        await _masters_with_schedule_kb(category),
        photo_url=SECTION_PHOTOS.get(category, SECTION_PHOTOS.get("booking")),
    )
    await callback.answer()


async def _get_salon_phone() -> str:
    from database import get_setting
    return await get_setting("salon_phone", "+7 (495) 123-45-67")


async def _masters_with_schedule_kb(category: str, back_cb: str = None):
    """Клавиатура выбора мастера из БД.
    back_cb — куда ведёт кнопка «Назад» (по умолчанию к выбору услуг).
    """
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    masters = await get_masters_by_category(category)
    buttons = []
    for m in masters:
        buttons.append([
            InlineKeyboardButton(
                text=m["name"],
                callback_data=f"book:master:{m['master_id']}",
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="👤 Любой мастер", callback_data="book:master:any")
    ])
    buttons.append([
        InlineKeyboardButton(
            text="◀️ Назад",
            callback_data=back_cb or f"book:back_to_services:{category}",
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ── Назад из выбора мастера к выбору услуги ──────────────

@router.callback_query(BookingStates.choosing_master, F.data.startswith("book:back_to_services:"))
async def cb_book_back_to_services(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    category = callback.data.split(":")[3]
    await state.update_data(category=category)
    await state.set_state(BookingStates.choosing_service)

    cat = await get_category_by_key(category) or {}
    lang = await get_user_lang(callback.from_user.id)
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        f"{cat.get('title', 'Услуги')}\n\n{t('booking_choose_service', lang)}",
        await services_list_kb(category),
        photo_url=SECTION_PHOTOS.get(category, SECTION_PHOTOS.get("booking")),
    )
    await callback.answer()


# ── Назад из выбора услуги к выбору мастера (флоу: мастер→услуга) ──

@router.callback_query(BookingStates.choosing_service, F.data.startswith("book:back_to_master:"))
async def cb_book_back_to_master_from_service(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    category = callback.data.split(":")[3]
    await state.set_state(BookingStates.choosing_master)

    lang = await get_user_lang(callback.from_user.id)
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        t("booking_choose_master", lang),
        await _masters_with_schedule_kb(category, back_cb=f"services:cat:{category}"),
        photo_url=SECTION_PHOTOS.get(category, SECTION_PHOTOS.get("booking")),
    )
    await callback.answer()


# ── Шаг 4: выбран мастер — показываем даты ───────────────

@router.callback_query(BookingStates.choosing_master, F.data.startswith("book:master:"))
async def cb_book_choose_master(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    from services.slots import get_available_dates

    master_raw = callback.data.split(":")[2]
    data = await state.get_data()
    category = data.get("category", "")
    duration = data.get("service_duration", 60)

    salon_phone = await _get_salon_phone()

    if master_raw == "any":
        # Ищем первого мастера с доступными датами из DB
        candidates = await get_masters_by_category(category)
        chosen_master_id = None
        chosen_dates = []
        for m in candidates:
            mid = m["master_id"]
            dates = await get_available_dates(mid)
            if dates:
                chosen_master_id = mid
                chosen_dates = dates
                break

        if not chosen_master_id:
            await callback.answer(
                f"К сожалению, в ближайшие 14 дней нет свободных окон. "
                f"Позвоните нам: {salon_phone}",
                show_alert=True,
            )
            return

        master_rec = await get_master(chosen_master_id)
        master_name = master_rec["name"] if master_rec else chosen_master_id
        master_id = chosen_master_id
        available_dates = chosen_dates
    else:
        master_rec = await get_master(master_raw)
        if not master_rec:
            await callback.answer("Мастер не найден", show_alert=True)
            return
        master_id = master_raw
        master_name = master_rec["name"]
        available_dates = await get_available_dates(master_id)

    if not available_dates:
        await callback.answer(
            f"К сожалению, в ближайшие 14 дней нет свободных дат. "
            f"Позвоните нам: {salon_phone}",
            show_alert=True,
        )
        return

    await state.update_data(
        master_id=master_id,
        master_name=master_name,
        menu_msg_id=callback.message.message_id,
    )

    data = await state.get_data()  # перечитываем — данные обновлены

    # Если пришли из категории (from_category_start) и услуга ещё не выбрана —
    # показываем список услуг. Иначе сразу к датам.
    if data.get("from_category_start") and not data.get("service_id"):
        category = data.get("category", "")
        lang = await get_user_lang(callback.from_user.id)
        cat = await get_category_by_key(category) or {}
        await state.set_state(BookingStates.choosing_service)
        await edit_menu(
            bot, callback.message.chat.id, callback.message.message_id,
            f"👤 <b>Мастер:</b> {master_name}\n\n"
            f"{cat.get('title', 'Услуги')}\n"
            f"{t('booking_choose_service', lang)}",
            await services_list_kb(category, back_cb=f"book:back_to_master:{category}"),
            photo_url=SECTION_PHOTOS.get(category, SECTION_PHOTOS.get("booking")),
        )
    else:
        await state.set_state(BookingStates.choosing_master)  # остаёмся для навигации через callback_data
        await edit_menu(
            bot, callback.message.chat.id, callback.message.message_id,
            f"👤 <b>Мастер:</b> {master_name}\n\n📅 <b>Выбери дату:</b>",
            dates_kb(available_dates, master_id),
            photo_url=SECTION_PHOTOS.get("booking"),
        )
    await callback.answer()


# ── Шаг 5: выбрана дата — показываем слоты ───────────────

@router.callback_query(F.data.startswith("book:date:"))
async def cb_book_choose_date(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    from services.slots import get_free_slots
    from datetime import date as date_cls

    # book:date:{master_id}:{YYYY-MM-DD}
    parts = callback.data.split(":")
    master_id = parts[2]
    date_str = parts[3]

    try:
        target_date = date_cls.fromisoformat(date_str)
    except ValueError:
        await callback.answer("Неверная дата", show_alert=True)
        return

    data = await state.get_data()
    duration = data.get("service_duration", 60)
    _m = await get_master(master_id)
    master_name = data.get("master_name") or (_m["name"] if _m else master_id)

    free_slots = await get_free_slots(master_id, target_date, duration)

    if not free_slots:
        await callback.answer(
            "На эту дату нет свободных слотов. Выбери другую дату.",
            show_alert=True,
        )
        return

    await state.update_data(
        master_id=master_id,
        master_name=master_name,
        date=date_str,
    )

    date_label = _fmt_date(target_date)
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        f"👤 <b>Мастер:</b> {master_name}\n"
        f"📅 <b>Дата:</b> {date_label}\n\n"
        f"⏰ <b>Выбери время:</b>",
        slots_kb(free_slots, master_id, date_str),
        photo_url=SECTION_PHOTOS.get("booking"),
    )
    await callback.answer()


# ── Назад к выбору даты ───────────────────────────────────

@router.callback_query(F.data.startswith("book:back:date:"))
async def cb_back_to_dates(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    from services.slots import get_available_dates

    master_id = callback.data.split(":")[3]
    data = await state.get_data()
    _m = await get_master(master_id)
    master_name = data.get("master_name") or (_m["name"] if _m else master_id)

    available_dates = await get_available_dates(master_id)
    if not available_dates:
        await callback.answer("Нет доступных дат", show_alert=True)
        return

    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        f"👤 <b>Мастер:</b> {master_name}\n\n📅 <b>Выбери дату:</b>",
        dates_kb(available_dates, master_id),
        photo_url=SECTION_PHOTOS.get("booking"),
    )
    await callback.answer()


# ── Назад к выбору мастера ────────────────────────────────

@router.callback_query(F.data == "book:back:master")
async def cb_back_to_master(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    data = await state.get_data()
    category = data.get("category", "")
    service_name = data.get("service_name", "")
    service_price = data.get("service_price", "")

    await state.set_state(BookingStates.choosing_master)
    lang = await get_user_lang(callback.from_user.id)
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        f"💅 <b>{service_name}</b> — {service_price}₽\n\n"
        f"{t('booking_choose_master', lang)}",
        await _masters_with_schedule_kb(category),
        photo_url=SECTION_PHOTOS.get("booking"),
    )
    await callback.answer()


# ── Шаг 6: выбран слот — запрашиваем телефон ─────────────

@router.callback_query(F.data.startswith("book:slot:"))
async def cb_book_choose_slot(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    # book:slot:{master_id}:{date}:{HH:MM}
    raw = callback.data
    prefix = "book:slot:"
    rest = raw[len(prefix):]
    parts = rest.split(":")
    master_id = parts[0]
    date_str = parts[1]
    time_str = f"{parts[2]}:{parts[3]}"

    await state.update_data(
        master_id=master_id,
        date=date_str,
        time_start=time_str,
    )

    lang = await get_user_lang(callback.from_user.id)
    stored_phone = await get_user_phone(callback.from_user.id)

    if stored_phone:
        # Телефон уже есть — спрашиваем подтверждение
        await state.update_data(phone=stored_phone)
        await state.set_state(BookingStates.confirming_phone)

        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        phone_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text=f"✅ Да, {stored_phone}", callback_data="booking:use_phone"),
                InlineKeyboardButton(text="✏️ Изменить номер",       callback_data="booking:change_phone"),
            ],
        ])
        await edit_menu(
            bot, callback.message.chat.id, callback.message.message_id,
            f"📞 <b>Использовать сохранённый номер?</b>\n\n<code>{stored_phone}</code>",
            phone_kb,
            photo_url=SECTION_PHOTOS.get("booking"),
        )
    else:
        # Телефон не сохранён — просим ввести
        await state.set_state(BookingStates.entering_phone)
        await edit_menu(
            bot, callback.message.chat.id, callback.message.message_id,
            t("booking_enter_phone", lang),
            _cancel_kb(),
            photo_url=SECTION_PHOTOS.get("booking"),
        )
    await callback.answer()


@router.callback_query(BookingStates.confirming_phone, F.data == "booking:use_phone")
async def cb_booking_use_stored_phone(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    """Клиент подтвердил использование сохранённого номера."""
    from datetime import date as date_cls
    data = await state.get_data()
    await state.set_state(BookingStates.confirming)

    date_str = data.get("date", "")
    try:
        target_date = date_cls.fromisoformat(date_str)
        date_formatted = _fmt_date(target_date)
    except (ValueError, TypeError):
        date_formatted = date_str

    confirm_text = (
        "✅ <b>Подтвердите запись</b>\n\n"
        f"💅 <b>Услуга:</b> {data.get('service_name', '—')} — {data.get('service_price', '—')}₽\n"
        f"👤 <b>Мастер:</b> {data.get('master_name', '—')}\n"
        f"📅 <b>Дата:</b> {date_formatted}\n"
        f"⏰ <b>Время:</b> {data.get('time_start', '—')}\n"
        f"⏱ <b>Длительность:</b> {data.get('service_duration', 0)} мин\n"
        f"📞 <b>Телефон:</b> {data.get('phone', '—')}\n\n"
        "Нажми ✅ для подтверждения"
    )
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        confirm_text,
        confirm_booking_kb(),
        photo_url=SECTION_PHOTOS.get("booking"),
    )
    await callback.answer()


@router.callback_query(BookingStates.confirming_phone, F.data == "booking:change_phone")
async def cb_booking_change_phone(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    """Клиент хочет ввести другой номер."""
    lang = await get_user_lang(callback.from_user.id)
    await state.set_state(BookingStates.entering_phone)
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        t("booking_enter_phone", lang),
        _cancel_kb(),
        photo_url=SECTION_PHOTOS.get("booking"),
    )
    await callback.answer()


# ── Шаг 7: получили телефон — показываем подтверждение ───

@router.message(BookingStates.entering_phone)
async def msg_booking_phone(message: Message, bot: Bot, state: FSMContext) -> None:
    from datetime import date as date_cls

    phone = message.text.strip()
    await state.update_data(phone=phone)
    await update_user_phone(message.from_user.id, phone)
    await state.set_state(BookingStates.confirming)

    try:
        await message.delete()
    except Exception:
        pass

    lang = await get_user_lang(message.from_user.id)
    data = await state.get_data()
    msg_id = data.get("menu_msg_id")

    date_str = data.get("date", "")
    time_str = data.get("time_start", "")
    duration = data.get("service_duration", 0)

    try:
        target_date = date_cls.fromisoformat(date_str)
        date_formatted = _fmt_date(target_date)
    except (ValueError, TypeError):
        date_formatted = date_str

    confirm_text = (
        "✅ <b>Подтвердите запись</b>\n\n"
        f"💅 <b>Услуга:</b> {data.get('service_name', '—')} — {data.get('service_price', '—')}₽\n"
        f"👤 <b>Мастер:</b> {data.get('master_name', '—')}\n"
        f"📅 <b>Дата:</b> {date_formatted}\n"
        f"⏰ <b>Время:</b> {time_str}\n"
        f"⏱ <b>Длительность:</b> {duration} мин\n"
        f"📞 <b>Телефон:</b> {phone}\n\n"
        "Нажми ✅ для подтверждения"
    )

    await edit_menu(
        bot, message.chat.id, msg_id,
        confirm_text, confirm_booking_kb(),
        photo_url=SECTION_PHOTOS.get("booking"),
    )


# ── Шаг 8а: подтверждение — сохраняем в БД ──────────────

@router.callback_query(BookingStates.confirming, F.data == "booking:confirm")
async def cb_booking_confirm(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    from datetime import date as date_cls

    data = await state.get_data()
    user = callback.from_user
    lang = await get_user_lang(user.id)

    # Берём имя из нашей БД (то, что клиент ввёл при регистрации)
    user_db = await get_user(user.id)
    client_name = (user_db or {}).get("full_name") or user.full_name or user.first_name or str(user.id)

    username_str = f"@{user.username}" if user.username else "без username"
    date_str = data.get("date", "")

    try:
        target_date = date_cls.fromisoformat(date_str)
        date_formatted = _fmt_date(target_date)
    except (ValueError, TypeError):
        date_formatted = date_str

    booking_id = await create_booking(
        user_id=user.id,
        user_name=client_name,
        username=username_str,
        service=data.get("service_name", "—"),
        service_id=data.get("service_id", ""),
        master=data.get("master_name", "—"),
        master_id=data.get("master_id", ""),
        date=date_str,
        time_start=data.get("time_start", ""),
        duration=data.get("service_duration", 0),
        phone=data.get("phone", "—"),
    )

    if booking_id is None:
        # Слот занят (race condition)
        await state.clear()
        await edit_menu(
            bot, callback.message.chat.id, callback.message.message_id,
            "⚠️ <b>Упс, этот слот только что заняли!</b>\n\n"
            "Пожалуйста, выберите другое время.",
            after_booking_kb(),
            photo_url=SECTION_PHOTOS.get("booking"),
        )
        await callback.answer("Слот занят, выберите другое время.", show_alert=True)
        return

    # Уведомляем мастера если привязан TG
    try:
        from database import get_master
        master_db = await get_master(data.get("master_id", ""))
        if master_db and master_db.get("telegram_user_id"):
            await bot.send_message(
                chat_id=master_db["telegram_user_id"],
                text=(
                    f"📋 <b>Новая запись!</b>\n\n"
                    f"👤 Клиент: {data.get('client_name', client_name)}\n"
                    f"💅 Услуга: {data.get('service_name', '—')}\n"
                    f"📅 {data.get('date', date_str)} в {data.get('time_start', '—')}\n"
                    f"📞 {data.get('phone', '—')}"
                ),
                parse_mode="HTML",
            )
    except Exception as e:
        logger.warning("Не удалось уведомить мастера: %s", e)

    # Лояльность: увеличить счётчик посещений
    try:
        from database import increment_visit_count
        visit_count = await increment_visit_count(user.id)
        if visit_count % 5 == 0:
            if lang == "en":
                loyalty_text = (
                    f"🎉 <b>Congratulations on your {visit_count}th visit!</b>\n\n"
                    "As a thank-you for your loyalty, we're giving you "
                    "<b>10% off</b> your next service.\n\n"
                    "Just show this message when booking 😊"
                )
            else:
                loyalty_text = (
                    f"🎉 <b>Поздравляем с {visit_count}-м визитом!</b>\n\n"
                    "В знак благодарности за вашу верность дарим вам "
                    "<b>скидку 10%</b> на следующую услугу.\n\n"
                    "Просто покажите это сообщение при записи 😊"
                )
            await bot.send_message(
                chat_id=user.id,
                text=loyalty_text,
                parse_mode="HTML",
            )
    except Exception as e:
        logger.warning("Лояльность: ошибка: %s", e)

    await state.clear()

    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        t("booking_success", lang),
        after_booking_kb(),
        photo_url=SECTION_PHOTOS.get("booking"),
    )
    # Явно обновляем last_msg_id — чтобы /start корректно отредактировал это сообщение
    await save_last_msg_id(callback.from_user.id, callback.message.message_id)
    await callback.answer("✅ Запись принята!")

    # Уведомление администратору — всегда на системном языке
    if ADMIN_ID:
        try:
            from database import get_system_lang
            sys_lang = await get_system_lang()
            admin_text = t(
                "admin_new_booking", sys_lang,
                user_name=client_name,
                username=f"@{callback.from_user.username}" if callback.from_user.username else "—",
                service=data.get('service_name', '—'),
                master=data.get('master_name', '—'),
                date_time=f"{date_formatted} {data.get('time_start', '—')}",
                phone=data.get('phone', '—'),
                booking_id=booking_id,
            )
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_text,
                reply_markup=admin_booking_kb(booking_id),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning("Не удалось отправить уведомление о записи: %s", e)


# ── Шаг 8б: отмена записи ───────────────────────────────

@router.callback_query(BookingStates.confirming, F.data == "booking:cancel")
async def cb_booking_cancel(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    await state.clear()
    lang = await get_user_lang(callback.from_user.id)
    from database import get_setting
    salon_name = await get_setting("salon_name", "Салон красоты")
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        t("main_menu_text", lang, name=callback.from_user.first_name, salon_name=salon_name),
        main_menu_kb(lang),
        photo_url=SECTION_PHOTOS.get("main"),
    )
    await callback.answer(t("booking_cancelled", lang))


# ── Отмена в любом шаге FSM ──────────────────────────────

@router.callback_query(F.data == "booking:cancel")
async def cb_booking_cancel_any(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    await state.clear()
    lang = await get_user_lang(callback.from_user.id)
    from database import get_setting
    salon_name = await get_setting("salon_name", "Салон красоты")
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        t("main_menu_text", lang, name=callback.from_user.first_name, salon_name=salon_name),
        main_menu_kb(lang),
        photo_url=SECTION_PHOTOS.get("main"),
    )
    await callback.answer()


# ── Управление записями из уведомления (для админа) ──────

@router.callback_query(F.data.startswith("admin_booking:"))
async def cb_admin_booking_action(callback: CallbackQuery, bot: Bot) -> None:
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    parts = callback.data.split(":")
    action = parts[1]        # confirm | cancel
    booking_id = int(parts[2])

    if action == "confirm":
        await update_booking_status(booking_id, "confirmed")
        status_text = "✅ Запись подтверждена"
    else:
        await update_booking_status(booking_id, "cancelled")
        status_text = "❌ Запись отменена"

    # ── Уведомляем клиента ────────────────────────────────
    booking = await get_booking(booking_id)
    if booking:
        client_id = booking["user_id"]
        if action == "confirm":
            client_text = (
                "✅ <b>Ваша запись подтверждена!</b>\n\n"
                f"💅 {booking['service']}\n"
                f"👤 Мастер: {booking['master']}\n"
                f"📅 {booking['date']} в {booking['time_start']}\n\n"
                "Ждём вас! 😊"
            )
            client_kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🏠 В меню", callback_data="notify:dismiss"),
            ]])
        else:
            client_text = (
                "❌ <b>Ваша запись отменена.</b>\n\n"
                f"💅 {booking['service']}\n"
                f"📅 {booking['date']} в {booking['time_start']}\n\n"
                "Если нужно — запишитесь снова или позвоните нам:\n"
                "📞 +7 (495) 123-45-67"
            )
            client_kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="📅 Записаться снова", callback_data="book:start"),
                InlineKeyboardButton(text="🏠 В меню",           callback_data="notify:dismiss"),
            ]])
        try:
            await bot.send_message(
                chat_id=client_id,
                text=client_text,
                reply_markup=client_kb,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning("Не удалось уведомить клиента %s: %s", client_id, e)

    # ── Обновляем сообщение у админа ─────────────────────
    try:
        original = callback.message.text or ""
        await callback.message.edit_text(
            original + f"\n\n<b>{status_text}</b>",
            reply_markup=None,
            parse_mode="HTML",
        )
    except Exception:
        pass
    await callback.answer(status_text)


# ── Возврат в главное меню из FSM ────────────────────────

@router.callback_query(BookingStates.choosing_category, F.data == "menu:main")
@router.callback_query(BookingStates.choosing_service, F.data == "menu:main")
@router.callback_query(BookingStates.choosing_master, F.data == "menu:main")
@router.callback_query(BookingStates.entering_phone, F.data == "menu:main")
@router.callback_query(BookingStates.confirming_phone, F.data == "menu:main")
@router.callback_query(BookingStates.confirming, F.data == "menu:main")
async def cb_fsm_back_to_main(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    await state.clear()
    lang = await get_user_lang(callback.from_user.id)
    from database import get_setting
    salon_name = await get_setting("salon_name", "Салон красоты")
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        t("main_menu_text", lang, name=callback.from_user.first_name, salon_name=salon_name),
        main_menu_kb(lang),
        photo_url=SECTION_PHOTOS.get("main"),
    )
    await callback.answer()
