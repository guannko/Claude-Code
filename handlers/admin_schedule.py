"""
Управление расписанием мастеров — только для ADMIN_ID.

callback_data схема:
  adm_sch:list                   — список мастеров
  adm_sch:master:{master_id}     — расписание мастера
  adm_sch:toggle:{master_id}:{d} — переключить день (0-6)
  adm_sch:hours:{master_id}      — изменить часы (FSM)
  adm_sch:dayoff:{master_id}     — добавить выходной (FSM)
  adm_sch:del_dayoff:{id}        — удалить выходной
"""

import logging
import re
from datetime import datetime

from aiogram import Router, Bot, F
from aiogram.filters import StateFilter
from aiogram.types import (
    CallbackQuery, Message,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext

from config import ADMIN_ID
from services.permissions import is_admin
from database import (
    get_master_schedule,
    toggle_master_day,
    update_master_all_hours,
    add_master_dayoff,
    get_master_dayoffs,
    delete_master_dayoff,
)
from database import get_all_masters_admin
from states import AdminScheduleStates

logger = logging.getLogger(__name__)
router = Router()

# Русские названия дней недели (короткие)
_DAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
# Русские названия месяцев (родительный падеж)
_MONTHS_GEN = [
    "", "янв", "фев", "мар", "апр", "май", "июн",
    "июл", "авг", "сен", "окт", "ноя", "дек",
]


# ══════════════════════════════════════════════════════════
#  Вспомогательные функции
# ══════════════════════════════════════════════════════════

async def _masters_list_kb() -> InlineKeyboardMarkup:
    """Клавиатура со списком мастеров из БД."""
    masters = await get_all_masters_admin()
    buttons = []
    for m in masters:
        buttons.append([
            InlineKeyboardButton(
                text=m["name"],
                callback_data=f"adm_sch:master:{m['master_id']}",
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="◀️ Закрыть", callback_data="admin:refresh"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _schedule_kb(master_id: str, schedule: list[dict]) -> InlineKeyboardMarkup:
    """Клавиатура расписания мастера — дни + управление."""
    # Строим словарь day_of_week -> is_working
    day_map = {row["day_of_week"]: row["is_working"] for row in schedule}

    # Ряд 1: Пн-Чт
    row1 = []
    for day in range(4):
        is_w = day_map.get(day, 0)
        icon = "✅" if is_w else "❌"
        row1.append(
            InlineKeyboardButton(
                text=f"{icon} {_DAYS_SHORT[day]}",
                callback_data=f"adm_sch:toggle:{master_id}:{day}",
            )
        )

    # Ряд 2: Пт-Вс
    row2 = []
    for day in range(4, 7):
        is_w = day_map.get(day, 0)
        icon = "✅" if is_w else "❌"
        row2.append(
            InlineKeyboardButton(
                text=f"{icon} {_DAYS_SHORT[day]}",
                callback_data=f"adm_sch:toggle:{master_id}:{day}",
            )
        )

    buttons = [
        row1,
        row2,
        [InlineKeyboardButton(text="⏰ Изменить часы", callback_data=f"adm_sch:hours:{master_id}")],
        [InlineKeyboardButton(text="📆 Добавить выходной", callback_data=f"adm_sch:dayoff:{master_id}")],
        [InlineKeyboardButton(text="◀️ Назад к мастерам", callback_data="adm_sch:list")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def _build_master_text(master_id: str) -> str:
    """Текст экрана расписания мастера."""
    from database import get_master as _get_master
    master_rec = await _get_master(master_id)
    master_name = master_rec["name"] if master_rec else master_id

    schedule = await get_master_schedule(master_id)
    dayoffs = await get_master_dayoffs(master_id)

    lines = [f"⚙️ <b>{master_name}</b> — расписание\n", "📅 <b>Рабочие дни:</b>"]
    for row in schedule:
        day = row["day_of_week"]
        if row["is_working"]:
            lines.append(
                f"✅ {_DAYS_SHORT[day]}  {row['start_time']}–{row['end_time']}"
            )
        else:
            lines.append(f"❌ {_DAYS_SHORT[day]}  выходной")

    lines.append("")
    lines.append("📆 <b>Запланированные выходные:</b>")
    if dayoffs:
        for d in dayoffs:
            try:
                dt = datetime.strptime(d["date"], "%Y-%m-%d")
                date_fmt = f"{dt.day} {_MONTHS_GEN[dt.month]}"
            except ValueError:
                date_fmt = d["date"]
            reason = d.get("reason") or "—"
            lines.append(f"• {date_fmt} — {reason}")
    else:
        lines.append("• нет запланированных выходных")

    return "\n".join(lines)


async def _dayoff_management_kb(master_id: str) -> InlineKeyboardMarkup:
    """Клавиатура со списком выходных для удаления + назад."""
    dayoffs = await get_master_dayoffs(master_id)
    buttons = []
    for d in dayoffs:
        try:
            dt = datetime.strptime(d["date"], "%Y-%m-%d")
            date_fmt = f"{dt.day} {_MONTHS_GEN[dt.month]}"
        except ValueError:
            date_fmt = d["date"]
        buttons.append([
            InlineKeyboardButton(
                text=f"❌ {date_fmt}",
                callback_data=f"adm_sch:del_dayoff:{d['id']}",
            )
        ])
    buttons.append([
        InlineKeyboardButton(
            text="◀️ Назад к расписанию",
            callback_data=f"adm_sch:master:{master_id}",
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ══════════════════════════════════════════════════════════
#  Handlers
# ══════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm_sch:list")
async def cb_sch_list(callback: CallbackQuery) -> None:
    if not await is_admin(callback.from_user.id):
        return await callback.answer()

    text = "👥 <b>Мастера</b>\n\nВыбери мастера для редактирования расписания:"
    kb = await _masters_list_kb()
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("adm_sch:master:"))
async def cb_sch_master(callback: CallbackQuery, state: FSMContext) -> None:
    if not await is_admin(callback.from_user.id):
        return await callback.answer()

    master_id = callback.data.split(":", 2)[2]
    from database import get_master as _get_master_rec
    if not await _get_master_rec(master_id):
        return await callback.answer("Мастер не найден", show_alert=True)

    schedule = await get_master_schedule(master_id)
    text = await _build_master_text(master_id)
    kb = _schedule_kb(master_id, schedule)

    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        msg = await callback.message.answer(text, reply_markup=kb)
        await state.update_data(sch_msg_id=msg.message_id)
    else:
        await state.update_data(sch_msg_id=callback.message.message_id)

    await callback.answer()


@router.callback_query(F.data.startswith("adm_sch:toggle:"))
async def cb_sch_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    if not await is_admin(callback.from_user.id):
        return await callback.answer()

    # adm_sch:toggle:{master_id}:{day}
    parts = callback.data.split(":")
    master_id = parts[2]
    day = int(parts[3])

    await toggle_master_day(master_id, day)

    schedule = await get_master_schedule(master_id)
    text = await _build_master_text(master_id)
    kb = _schedule_kb(master_id, schedule)

    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("adm_sch:hours:"))
async def cb_sch_hours(callback: CallbackQuery, state: FSMContext) -> None:
    if not await is_admin(callback.from_user.id):
        return await callback.answer()

    master_id = callback.data.split(":", 2)[2]
    await state.set_state(AdminScheduleStates.entering_hours)
    await state.update_data(
        sch_master_id=master_id,
        sch_msg_id=callback.message.message_id,
        sch_chat_id=callback.message.chat.id,
    )

    try:
        await callback.message.edit_text(
            "⏰ <b>Изменение часов работы</b>\n\n"
            "Введи часы работы в формате <code>ЧЧ:ММ-ЧЧ:ММ</code>\n"
            "Например: <code>10:00-20:00</code>\n\n"
            "Будет применено ко всем рабочим дням мастера.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="◀️ Отмена",
                    callback_data=f"adm_sch:master:{master_id}",
                )
            ]]),
        )
    except Exception:
        pass
    await callback.answer()


@router.message(AdminScheduleStates.entering_hours)
async def msg_sch_hours(message: Message, bot: Bot, state: FSMContext) -> None:
    if not await is_admin(message.from_user.id):
        return

    text = message.text.strip() if message.text else ""
    # Удаляем сообщение пользователя
    try:
        await message.delete()
    except Exception:
        pass

    data = await state.get_data()
    master_id = data.get("sch_master_id", "")
    msg_id = data.get("sch_msg_id")
    chat_id = data.get("sch_chat_id") or message.chat.id

    # Валидация формата ЧЧ:ММ-ЧЧ:ММ
    match = re.fullmatch(r"(\d{1,2}:\d{2})-(\d{1,2}:\d{2})", text)
    if not match:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text="❌ Неверный формат. Введи в формате <code>ЧЧ:ММ-ЧЧ:ММ</code>\n"
                     "Например: <code>10:00-20:00</code>",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(
                        text="◀️ Отмена",
                        callback_data=f"adm_sch:master:{master_id}",
                    )
                ]]),
            )
        except Exception:
            pass
        return

    start_str, end_str = match.group(1), match.group(2)

    # Проверяем что start < end
    try:
        start_dt = datetime.strptime(start_str, "%H:%M")
        end_dt = datetime.strptime(end_str, "%H:%M")
        if start_dt >= end_dt:
            raise ValueError("start >= end")
    except ValueError:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text="❌ Начало должно быть раньше конца. Попробуй снова:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(
                        text="◀️ Отмена",
                        callback_data=f"adm_sch:master:{master_id}",
                    )
                ]]),
            )
        except Exception:
            pass
        return

    await update_master_all_hours(master_id, start_str, end_str)
    await state.clear()

    # Возвращаем экран расписания мастера
    schedule = await get_master_schedule(master_id)
    master_text = await _build_master_text(master_id)
    kb = _schedule_kb(master_id, schedule)

    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=master_text,
            reply_markup=kb,
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("adm_sch:dayoff:"))
async def cb_sch_dayoff(callback: CallbackQuery, state: FSMContext) -> None:
    if not await is_admin(callback.from_user.id):
        return await callback.answer()

    master_id = callback.data.split(":", 2)[2]
    await state.set_state(AdminScheduleStates.entering_dayoff)
    await state.update_data(
        sch_master_id=master_id,
        sch_msg_id=callback.message.message_id,
        sch_chat_id=callback.message.chat.id,
    )

    dayoff_kb = await _dayoff_management_kb(master_id)

    try:
        await callback.message.edit_text(
            "📆 <b>Добавить выходной день</b>\n\n"
            "Введи дату в формате <code>ДД.ММ.ГГГГ</code>\n"
            "Например: <code>15.04.2026</code>\n\n"
            "Текущие выходные (нажми ❌ чтобы удалить):",
            reply_markup=dayoff_kb,
        )
    except Exception:
        pass
    await callback.answer()


@router.message(AdminScheduleStates.entering_dayoff)
async def msg_sch_dayoff(message: Message, bot: Bot, state: FSMContext) -> None:
    if not await is_admin(message.from_user.id):
        return

    text = message.text.strip() if message.text else ""
    try:
        await message.delete()
    except Exception:
        pass

    data = await state.get_data()
    master_id = data.get("sch_master_id", "")
    msg_id = data.get("sch_msg_id")
    chat_id = data.get("sch_chat_id") or message.chat.id

    # Парсим ДД.ММ.ГГГГ
    match = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{4})", text)
    if not match:
        dayoff_kb = await _dayoff_management_kb(master_id)
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text="❌ Неверный формат даты. Введи в формате <code>ДД.ММ.ГГГГ</code>\n"
                     "Например: <code>15.04.2026</code>\n\n"
                     "Текущие выходные:",
                reply_markup=dayoff_kb,
            )
        except Exception:
            pass
        return

    day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
    try:
        parsed_dt = datetime(year, month, day)
    except ValueError:
        dayoff_kb = await _dayoff_management_kb(master_id)
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text="❌ Такой даты не существует. Попробуй снова:\n\n"
                     "Текущие выходные:",
                reply_markup=dayoff_kb,
            )
        except Exception:
            pass
        return

    date_iso = parsed_dt.strftime("%Y-%m-%d")
    await add_master_dayoff(master_id, date_iso)
    await state.clear()

    # Возвращаем экран расписания мастера
    schedule = await get_master_schedule(master_id)
    master_text = await _build_master_text(master_id)
    kb = _schedule_kb(master_id, schedule)

    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=master_text,
            reply_markup=kb,
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("adm_sch:del_dayoff:"))
async def cb_sch_del_dayoff(callback: CallbackQuery, state: FSMContext) -> None:
    if not await is_admin(callback.from_user.id):
        return await callback.answer()

    dayoff_id = int(callback.data.split(":")[2])
    await delete_master_dayoff(dayoff_id)

    # Определяем master_id из FSM или пробуем найти в тексте
    data = await state.get_data()
    master_id = data.get("sch_master_id", "")

    # Если master_id в состоянии — обновляем список выходных
    if master_id:
        dayoff_kb = await _dayoff_management_kb(master_id)
        try:
            await callback.message.edit_reply_markup(reply_markup=dayoff_kb)
        except Exception:
            pass
    await callback.answer("✅ Выходной удалён")


# ── Сброс FSM при нажатии "Назад к расписанию" в режиме dayoff ──

@router.callback_query(
    StateFilter(AdminScheduleStates.entering_dayoff, AdminScheduleStates.entering_hours),
    F.data.startswith("adm_sch:master:"),
)
async def cb_sch_cancel_fsm(callback: CallbackQuery, state: FSMContext) -> None:
    if not await is_admin(callback.from_user.id):
        return await callback.answer()

    await state.clear()
    master_id = callback.data.split(":", 2)[2]

    schedule = await get_master_schedule(master_id)
    text = await _build_master_text(master_id)
    kb = _schedule_kb(master_id, schedule)

    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        pass
    await callback.answer()
