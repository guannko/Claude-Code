"""
Управление рабочими слотами мастера на конкретный день.

Мастер сам определяет свободные окна на день — именно эти слоты
видят клиенты при записи. Если слоты не заданы вручную, система
использует автогенерацию из расписания (как раньше).

callback_data:
  mst_day:home                   — показ на сегодня/завтра
  mst_day:date:{YYYY-MM-DD}      — слоты на конкретную дату
  mst_day:add:{YYYY-MM-DD}       — добавить слот (ввод времени)
  mst_day:gen:{YYYY-MM-DD}       — сгенерировать из расписания
  mst_day:del:{slot_id}:{date}   — удалить слот
  mst_day:clear:{YYYY-MM-DD}     — очистить все незанятые слоты
"""

import logging
from datetime import date, timedelta

from aiogram import Router, Bot, F
from aiogram.types import (
    CallbackQuery, Message,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from database import (
    get_master_by_telegram_id,
    get_master_custom_slots, has_master_custom_slots,
    add_master_custom_slot, delete_master_custom_slot, clear_master_custom_slots,
    get_booked_slots,
)
from services.slots import get_all_slots
from services.sender import edit_menu
from data.salon import SECTION_PHOTOS
from states import MasterDayStates

logger = logging.getLogger(__name__)
router = Router()

_PHOTO = SECTION_PHOTOS.get("masters")
_WEEKDAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def _fmt_date(d: date) -> str:
    today = date.today()
    if d == today:
        return f"сегодня {d.strftime('%d.%m')} ({_WEEKDAYS_RU[d.weekday()]})"
    if d == today + timedelta(days=1):
        return f"завтра {d.strftime('%d.%m')} ({_WEEKDAYS_RU[d.weekday()]})"
    return f"{d.strftime('%d.%m')} ({_WEEKDAYS_RU[d.weekday()]})"


async def _build_day_view(master_id: str, date_str: str) -> tuple[str, InlineKeyboardMarkup]:
    """Текст и клавиатура для управления слотами на дату."""
    target = date.fromisoformat(date_str)
    date_label = _fmt_date(target)

    custom_slots = await get_master_custom_slots(master_id, date_str)
    booked_raw = await get_booked_slots(master_id, date_str)
    booked_times = {b["time_start"] for b in booked_raw}

    is_custom = bool(custom_slots)

    # Строим текст
    lines = [f"📅 <b>Слоты на {date_label}</b>\n"]

    if is_custom:
        lines.append(f"✏️ <i>Ручное расписание ({len(custom_slots)} слотов)</i>")
        for s in custom_slots:
            t = s["time_start"]
            mark = "🔒 забронирован" if t in booked_times else "🟢 свободен"
            lines.append(f"  {t} — {mark}")
    else:
        lines.append("⚙️ <i>Расписание автоматическое (из настроек)</i>")
        lines.append("Нажмите «Ручной режим» чтобы задать своё.")

    text = "\n".join(lines)

    # Клавиатура
    rows = []

    # Навигация по датам
    today = date.today()
    date_row = []
    for delta in range(4):
        d = today + timedelta(days=delta)
        label = ["Сег", "Завтра", d.strftime("%d.%m"), d.strftime("%d.%m")][delta] if delta < 2 else d.strftime("%d.%m")
        active = "✅ " if d.isoformat() == date_str else ""
        date_row.append(InlineKeyboardButton(
            text=f"{active}{label}",
            callback_data=f"mst_day:date:{d.isoformat()}"
        ))
    rows.append(date_row)

    # Действия
    rows.append([
        InlineKeyboardButton(text="➕ Добавить слот",  callback_data=f"mst_day:add:{date_str}"),
        InlineKeyboardButton(text="⚙️ Из расписания", callback_data=f"mst_day:gen:{date_str}"),
    ])
    if is_custom:
        rows.append([
            InlineKeyboardButton(text="🗑 Очистить свободные", callback_data=f"mst_day:clear:{date_str}"),
        ])

    # Кнопки удаления для незабронированных слотов
    free_slots = [s for s in custom_slots if s["time_start"] not in booked_times]
    if free_slots:
        rows.append([InlineKeyboardButton(
            text=f"❌ {s['time_start']}",
            callback_data=f"mst_day:del:{s['id']}:{date_str}"
        ) for s in free_slots[:6]])  # max 6 в ряду слишком много, разбиваем
        # Если слотов много — по 3 в строке
        if len(free_slots) > 3:
            rows.pop()
            for i in range(0, min(len(free_slots), 12), 3):
                chunk = free_slots[i:i+3]
                rows.append([InlineKeyboardButton(
                    text=f"❌ {s['time_start']}",
                    callback_data=f"mst_day:del:{s['id']}:{date_str}"
                ) for s in chunk])

    rows.append([InlineKeyboardButton(text="◀️ Панель мастера", callback_data="mst_panel:home")])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


# ── Главный экран ───────────────────────────────────────────

@router.callback_query(F.data == "mst_day:home")
async def cb_mst_day_home(callback: CallbackQuery, bot: Bot) -> None:
    master = await get_master_by_telegram_id(callback.from_user.id)
    if not master:
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    date_str = date.today().isoformat()
    text, kb = await _build_day_view(master["master_id"], date_str)
    await edit_menu(bot, callback.message.chat.id, callback.message.message_id,
                    text, kb, photo_url=_PHOTO)
    await callback.answer()


@router.callback_query(F.data.startswith("mst_day:date:"))
async def cb_mst_day_date(callback: CallbackQuery, bot: Bot) -> None:
    master = await get_master_by_telegram_id(callback.from_user.id)
    if not master:
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    date_str = callback.data[len("mst_day:date:"):]
    text, kb = await _build_day_view(master["master_id"], date_str)
    await edit_menu(bot, callback.message.chat.id, callback.message.message_id,
                    text, kb, photo_url=_PHOTO)
    await callback.answer()


# ── Добавить слот вручную ───────────────────────────────────

@router.callback_query(F.data.startswith("mst_day:add:"))
async def cb_mst_day_add(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    master = await get_master_by_telegram_id(callback.from_user.id)
    if not master:
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    date_str = callback.data[len("mst_day:add:"):]
    await state.set_state(MasterDayStates.entering_slot_time)
    await state.update_data(master_id=master["master_id"], slot_date=date_str)

    target = date.fromisoformat(date_str)
    date_label = _fmt_date(target)

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Отмена", callback_data=f"mst_day:date:{date_str}"),
    ]])
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        f"⏰ <b>Добавить слот — {date_label}</b>\n\n"
        "Введите время в формате <b>ЧЧ:ММ</b>\n"
        "Например: <code>10:00</code> или <code>14:30</code>\n\n"
        "Можно отправить несколько через запятую:\n"
        "<code>10:00, 11:30, 13:00, 15:30</code>",
        kb, photo_url=_PHOTO,
    )
    await callback.answer()


@router.message(StateFilter(MasterDayStates.entering_slot_time))
async def msg_mst_slot_time(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    master_id = data.get("master_id", "")
    date_str = data.get("slot_date", date.today().isoformat())

    raw = (message.text or "").strip()
    time_parts = [t.strip() for t in raw.replace(" ", "").replace(";", ",").split(",")]

    added = []
    errors = []
    for t in time_parts:
        # Нормализуем: "9:00" → "09:00"
        try:
            parts = t.split(":")
            h = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 else 0
            assert 0 <= h <= 23 and 0 <= m <= 59
            normalized = f"{h:02d}:{m:02d}"
        except Exception:
            errors.append(t)
            continue

        ok = await add_master_custom_slot(master_id, date_str, normalized)
        if ok:
            added.append(normalized)
        else:
            errors.append(f"{normalized} (уже есть)")

    await state.clear()
    try:
        await message.delete()
    except Exception:
        pass

    msg_parts = []
    if added:
        msg_parts.append(f"✅ Добавлено: {', '.join(added)}")
    if errors:
        msg_parts.append(f"⚠️ Ошибка/дубль: {', '.join(errors)}")

    await message.answer("\n".join(msg_parts) if msg_parts else "Ничего не добавлено.")

    # Обновляем вид — редактируем старое сообщение меню
    from database import get_last_msg_id
    last_id = await get_last_msg_id(message.from_user.id)
    if last_id:
        text, kb = await _build_day_view(master_id, date_str)
        try:
            await edit_menu(bot, message.chat.id, last_id, text, kb, photo_url=_PHOTO)
        except Exception:
            pass


# ── Сгенерировать из расписания ─────────────────────────────

@router.callback_query(F.data.startswith("mst_day:gen:"))
async def cb_mst_day_gen(callback: CallbackQuery, bot: Bot) -> None:
    master = await get_master_by_telegram_id(callback.from_user.id)
    if not master:
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    date_str = callback.data[len("mst_day:gen:"):]
    target = date.fromisoformat(date_str)
    master_id = master["master_id"]

    # Генерируем из расписания (интервал 30 мин)
    auto_slots = await get_all_slots(master_id, target, duration_minutes=30)
    if not auto_slots:
        await callback.answer("Нет рабочих часов для этой даты.", show_alert=True)
        return

    added = 0
    for t in auto_slots:
        ok = await add_master_custom_slot(master_id, date_str, t)
        if ok:
            added += 1

    await callback.answer(f"✅ Сгенерировано {added} слотов", show_alert=False)
    text, kb = await _build_day_view(master_id, date_str)
    await edit_menu(bot, callback.message.chat.id, callback.message.message_id,
                    text, kb, photo_url=_PHOTO)


# ── Удалить слот ────────────────────────────────────────────

@router.callback_query(F.data.startswith("mst_day:del:"))
async def cb_mst_day_del(callback: CallbackQuery, bot: Bot) -> None:
    master = await get_master_by_telegram_id(callback.from_user.id)
    if not master:
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    # mst_day:del:{slot_id}:{date}
    parts = callback.data.split(":")
    slot_id = int(parts[2])
    date_str = f"{parts[3]}:{parts[4]}:{parts[5]}" if len(parts) >= 6 else parts[3]

    await delete_master_custom_slot(slot_id)
    await callback.answer("Слот удалён.")
    text, kb = await _build_day_view(master["master_id"], date_str)
    await edit_menu(bot, callback.message.chat.id, callback.message.message_id,
                    text, kb, photo_url=_PHOTO)


# ── Очистить все свободные слоты ────────────────────────────

@router.callback_query(F.data.startswith("mst_day:clear:"))
async def cb_mst_day_clear(callback: CallbackQuery, bot: Bot) -> None:
    master = await get_master_by_telegram_id(callback.from_user.id)
    if not master:
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    date_str = callback.data[len("mst_day:clear:"):]
    await clear_master_custom_slots(master["master_id"], date_str)
    await callback.answer("✅ Свободные слоты очищены.")
    text, kb = await _build_day_view(master["master_id"], date_str)
    await edit_menu(bot, callback.message.chat.id, callback.message.message_id,
                    text, kb, photo_url=_PHOTO)
