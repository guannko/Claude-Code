"""
Генерация доступных слотов для записи.
Слот свободен если:
  1. Мастер работает в этот день
  2. Слот + duration услуги не выходят за конец рабочего дня
  3. В этом промежутке нет подтверждённых/ожидающих записей в БД
"""
from datetime import date, datetime, timedelta
from data.salon import SLOT_INTERVAL, BOOKING_DAYS_AHEAD


async def get_available_dates(master_id: str) -> list[date]:
    """Даты когда мастер работает (из БД), исключая dayoffs."""
    from database.db import get_master_schedule, get_master_dayoffs
    schedule = await get_master_schedule(master_id)
    dayoffs_raw = await get_master_dayoffs(master_id)
    dayoff_dates = {d["date"] for d in dayoffs_raw}

    working_days = {row["day_of_week"] for row in schedule if row["is_working"]}
    today = date.today()
    result = []
    for i in range(1, BOOKING_DAYS_AHEAD + 1):
        d = today + timedelta(days=i)
        if d.weekday() in working_days and d.isoformat() not in dayoff_dates:
            result.append(d)
    return result


async def get_all_slots(master_id: str, target_date: date, duration_minutes: int) -> list[str]:
    """Все теоретические слоты из БД расписания."""
    from database.db import get_master_schedule, get_master_dayoffs
    schedule = await get_master_schedule(master_id)
    dayoffs_raw = await get_master_dayoffs(master_id)
    dayoff_dates = {d["date"] for d in dayoffs_raw}

    if target_date.isoformat() in dayoff_dates:
        return []

    day_row = next(
        (r for r in schedule if r["day_of_week"] == target_date.weekday() and r["is_working"]),
        None,
    )
    if not day_row:
        return []

    start_h, start_m = map(int, day_row["start_time"].split(":"))
    end_h, end_m = map(int, day_row["end_time"].split(":"))

    slots = []
    current = datetime(target_date.year, target_date.month, target_date.day, start_h, start_m)
    end_dt = datetime(target_date.year, target_date.month, target_date.day, end_h, end_m)

    while True:
        slot_end = current + timedelta(minutes=duration_minutes)
        if slot_end > end_dt:
            break
        slots.append(current.strftime("%H:%M"))
        current += timedelta(minutes=SLOT_INTERVAL)

    return slots


async def get_free_slots(master_id: str, target_date: date, duration_minutes: int) -> list[str]:
    """
    Свободные слоты = все слоты минус занятые из БД.

    Если у мастера есть кастомные слоты на эту дату — используем их.
    Иначе — автогенерация из расписания.
    """
    from database.db import get_booked_slots, has_master_custom_slots, get_master_custom_slots

    date_str = target_date.isoformat()
    if await has_master_custom_slots(master_id, date_str):
        custom = await get_master_custom_slots(master_id, date_str)
        all_slots = [s["time_start"] for s in custom]
    else:
        all_slots = await get_all_slots(master_id, target_date, duration_minutes)

    if not all_slots:
        return []

    booked = await get_booked_slots(master_id, date_str)

    def is_busy(slot_time: str) -> bool:
        slot_dt = datetime.strptime(slot_time, "%H:%M")
        slot_end = slot_dt + timedelta(minutes=duration_minutes)
        for b in booked:
            b_start = datetime.strptime(b["time_start"], "%H:%M")
            b_end = b_start + timedelta(minutes=b["duration"] or duration_minutes)
            if slot_dt < b_end and slot_end > b_start:
                return True
        return False

    return [s for s in all_slots if not is_busy(s)]
