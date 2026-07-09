"""
Все операции с базой данных — только здесь.
Supabase PostgreSQL вместо SQLite. Функции сохраняют те же сигнатуры.
"""

import logging
from typing import Any
from supabase import acreate_client, AsyncClient
from config import SUPABASE_URL, SUPABASE_KEY

logger = logging.getLogger(__name__)

_client: AsyncClient | None = None


async def _db() -> AsyncClient:
    global _client
    if _client is None:
        _client = await acreate_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


# ════════════════════════════════════════════════════════
#  Инициализация (seed при первом запуске)
# ════════════════════════════════════════════════════════

async def init_db() -> None:
    """Инициализация — seed данных если таблицы пустые."""
    logger.info("Подключение к Supabase...")
    await _db()
    await seed_master_schedules()
    await seed_masters()
    await seed_master_photos()
    await seed_salon_settings()
    await seed_services()
    logger.info("Supabase инициализирован")


# ════════════════════════════════════════════════════════
#  Пользователи
# ════════════════════════════════════════════════════════

async def get_user(user_id: int) -> dict | None:
    db = await _db()
    res = await db.table("bot_users").select("*").eq("user_id", user_id).maybe_single().execute()
    return res.data


async def register_user(user_id: int, username: str, full_name: str, lang: str) -> None:
    db = await _db()
    try:
        await db.table("bot_users").insert({
            "user_id": user_id, "username": username,
            "full_name": full_name, "lang": lang,
        }).execute()
    except Exception:
        pass  # уже существует


async def update_user_lang(user_id: int, lang: str) -> None:
    db = await _db()
    await db.table("bot_users").update({"lang": lang}).eq("user_id", user_id).execute()


async def get_user_lang(user_id: int) -> str:
    user = await get_user(user_id)
    return user["lang"] if user else "ru"


async def update_user_name(user_id: int, full_name: str) -> None:
    db = await _db()
    await db.table("bot_users").update({"full_name": full_name}).eq("user_id", user_id).execute()


async def update_user_phone(user_id: int, phone: str) -> None:
    db = await _db()
    await db.table("bot_users").update({"phone": phone}).eq("user_id", user_id).execute()


async def get_user_phone(user_id: int) -> str | None:
    user = await get_user(user_id)
    return user.get("phone") if user else None


async def get_last_photo_msg_id(user_id: int) -> int | None:
    user = await get_user(user_id)
    return user.get("last_photo_msg_id") if user else None


async def save_last_photo_msg_id(user_id: int, msg_id: int) -> None:
    db = await _db()
    await db.table("bot_users").update({"last_photo_msg_id": msg_id}).eq("user_id", user_id).execute()


async def get_last_msg_id(user_id: int) -> int | None:
    user = await get_user(user_id)
    return user["last_msg_id"] if user else None


async def save_last_msg_id(user_id: int, msg_id: int) -> None:
    db = await _db()
    await db.table("bot_users").update({"last_msg_id": msg_id}).eq("user_id", user_id).execute()


# ════════════════════════════════════════════════════════
#  Статистика
# ════════════════════════════════════════════════════════

async def get_users_count() -> int:
    db = await _db()
    res = await db.table("bot_users").select("user_id", count="exact").execute()
    return res.count or 0


async def get_today_users_count() -> int:
    db = await _db()
    from datetime import date
    today = date.today().isoformat()
    res = await db.table("bot_users").select("user_id", count="exact").gte("created_at", today).execute()
    return res.count or 0


async def get_last_user() -> dict | None:
    db = await _db()
    res = await db.table("bot_users").select("*").order("created_at", desc=True).limit(1).execute()
    return res.data[0] if res.data else None


async def get_recent_users(limit: int = 10) -> list[dict]:
    db = await _db()
    res = await db.table("bot_users").select("*").order("created_at", desc=True).limit(limit).execute()
    return res.data or []


async def get_all_users_paginated(limit: int = 20, offset: int = 0) -> list[dict]:
    db = await _db()
    res = await db.table("bot_users").select("*").order("created_at", desc=True).range(offset, offset + limit - 1).execute()
    return res.data or []


async def get_users_total_count() -> int:
    return await get_users_count()


# ════════════════════════════════════════════════════════
#  Записи на приём (bookings)
# ════════════════════════════════════════════════════════

def _add_minutes_str(time_str: str, minutes: int) -> str:
    h, m = map(int, time_str.split(":"))
    total = h * 60 + m + minutes
    return f"{total // 60:02d}:{total % 60:02d}"


async def get_booked_slots(master_id: str, date_str: str) -> list[dict]:
    db = await _db()
    res = await (db.table("bot_bookings")
                 .select("time_start,duration")
                 .eq("master_id", master_id)
                 .eq("date", date_str)
                 .neq("status", "cancelled")
                 .execute())
    return res.data or []


async def create_booking(
    user_id: int, user_name: str, username: str,
    service: str, service_id: str, master: str, master_id: str,
    date: str, time_start: str, duration: int, phone: str,
) -> int | None:
    db = await _db()
    slots = await get_booked_slots(master_id, date)
    new_end = _add_minutes_str(time_start, duration)
    for slot in slots:
        if slot.get("status") in ("cancelled", "rejected"):
            continue
        existing_end = _add_minutes_str(slot["time_start"], slot["duration"] or 60)
        if slot["time_start"] < new_end and existing_end > time_start:
            logger.warning("Слот занят: master=%s date=%s time=%s", master_id, date, time_start)
            return None

    date_time = f"{date} {time_start}" if date and time_start else ""
    res = await db.table("bot_bookings").insert({
        "user_id": user_id, "user_name": user_name, "username": username,
        "service": service, "service_id": service_id,
        "master": master, "master_id": master_id,
        "date": date, "time_start": time_start, "duration": duration,
        "date_time": date_time, "phone": phone,
    }).execute()
    return res.data[0]["id"] if res.data else None


async def get_user_bookings(user_id: int) -> list[dict]:
    db = await _db()
    res = await db.table("bot_bookings").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
    return res.data or []


async def get_all_bookings(limit: int = 20) -> list[dict]:
    db = await _db()
    res = await db.table("bot_bookings").select("*").order("created_at", desc=True).limit(limit).execute()
    return res.data or []


async def get_pending_bookings_count() -> int:
    db = await _db()
    res = await db.table("bot_bookings").select("id", count="exact").eq("status", "new").execute()
    return res.count or 0


async def get_pending_bookings(limit: int = 10) -> list[dict]:
    db = await _db()
    res = await (db.table("bot_bookings")
                 .select("*").eq("status", "new")
                 .order("created_at", desc=True).limit(limit).execute())
    return res.data or []


async def get_bookings_for_tomorrow() -> list[dict]:
    from datetime import date, timedelta
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    db = await _db()
    res = await (db.table("bot_bookings")
                 .select("*")
                 .eq("date", tomorrow)
                 .not_.in_("status", ["cancelled", "rejected"])
                 .order("time_start").execute())
    return res.data or []


async def get_upcoming_bookings_for_master(master_id: str, limit: int = 10) -> list[dict]:
    from datetime import date as _date
    today = _date.today().isoformat()
    db = await _db()
    res = await (db.table("bot_bookings")
                 .select("*")
                 .eq("master_id", master_id)
                 .gte("date", today)
                 .not_.in_("status", ["cancelled", "rejected"])
                 .order("date").order("time_start")
                 .limit(limit).execute())
    return res.data or []


async def get_bookings_count() -> int:
    db = await _db()
    res = await db.table("bot_bookings").select("id", count="exact").execute()
    return res.count or 0


async def get_today_bookings_count() -> int:
    from datetime import date
    today = date.today().isoformat()
    db = await _db()
    res = await db.table("bot_bookings").select("id", count="exact").gte("created_at", today).execute()
    return res.count or 0


async def get_booking(booking_id: int) -> dict | None:
    db = await _db()
    res = await db.table("bot_bookings").select("*").eq("id", booking_id).maybe_single().execute()
    return res.data


async def update_booking_status(booking_id: int, status: str) -> None:
    db = await _db()
    await db.table("bot_bookings").update({"status": status}).eq("id", booking_id).execute()


async def update_booking_attended(booking_id: int, attended: int) -> None:
    db = await _db()
    await db.table("bot_bookings").update({"attended": attended}).eq("id", booking_id).execute()


# ════════════════════════════════════════════════════════
#  Расписание мастеров
# ════════════════════════════════════════════════════════

async def seed_master_schedules() -> None:
    from data.salon import MASTER_SCHEDULE
    db = await _db()
    res = await db.table("bot_master_schedules").select("master_id", count="exact").execute()
    if (res.count or 0) > 0:
        return
    rows = []
    for master_id, info in MASTER_SCHEDULE.items():
        for day in range(7):
            rows.append({
                "master_id": master_id, "day_of_week": day,
                "start_time": info["start"], "end_time": info["end"],
                "is_working": 1 if day in info["working_days"] else 0,
            })
    if rows:
        await db.table("bot_master_schedules").upsert(rows).execute()
    logger.info("Расписание мастеров перенесено в Supabase")


async def get_master_schedule(master_id: str) -> list[dict]:
    db = await _db()
    res = await db.table("bot_master_schedules").select("*").eq("master_id", master_id).order("day_of_week").execute()
    return res.data or []


async def toggle_master_day(master_id: str, day_of_week: int) -> int:
    db = await _db()
    res = await db.table("bot_master_schedules").select("is_working").eq("master_id", master_id).eq("day_of_week", day_of_week).maybe_single().execute()
    current = res.data["is_working"] if res.data else 1
    new_val = 0 if current else 1
    await db.table("bot_master_schedules").update({"is_working": new_val}).eq("master_id", master_id).eq("day_of_week", day_of_week).execute()
    return new_val


async def update_master_hours(master_id: str, day_of_week: int, start: str, end: str) -> None:
    db = await _db()
    await db.table("bot_master_schedules").update({"start_time": start, "end_time": end}).eq("master_id", master_id).eq("day_of_week", day_of_week).execute()


async def update_master_all_hours(master_id: str, start: str, end: str) -> None:
    db = await _db()
    await db.table("bot_master_schedules").update({"start_time": start, "end_time": end}).eq("master_id", master_id).eq("is_working", 1).execute()


async def add_master_dayoff(master_id: str, date: str, reason: str = "") -> None:
    db = await _db()
    try:
        await db.table("bot_master_dayoffs").insert({"master_id": master_id, "date": date, "reason": reason}).execute()
    except Exception:
        pass


async def get_master_dayoffs(master_id: str) -> list[dict]:
    from datetime import date
    today = date.today().isoformat()
    db = await _db()
    res = await db.table("bot_master_dayoffs").select("*").eq("master_id", master_id).gte("date", today).order("date").execute()
    return res.data or []


async def delete_master_dayoff(dayoff_id: int) -> None:
    db = await _db()
    await db.table("bot_master_dayoffs").delete().eq("id", dayoff_id).execute()


# ════════════════════════════════════════════════════════
#  Профили мастеров
# ════════════════════════════════════════════════════════

async def seed_masters() -> None:
    from data.salon import MASTER_SCHEDULE
    db = await _db()
    res = await db.table("bot_masters").select("master_id", count="exact").execute()
    if (res.count or 0) > 0:
        return
    rows = [{"master_id": mid, "name": info["name"], "category": info["category"]}
            for mid, info in MASTER_SCHEDULE.items()]
    if rows:
        await db.table("bot_masters").upsert(rows).execute()
    logger.info("Профили мастеров перенесены в Supabase")


async def seed_master_photos() -> None:
    from data.salon import MASTER_PHOTOS
    db = await _db()
    for master_id, photo_url in MASTER_PHOTOS.items():
        res = await db.table("bot_masters").select("photo_file_id").eq("master_id", master_id).maybe_single().execute()
        if res.data and not res.data.get("photo_file_id"):
            await db.table("bot_masters").update({"photo_file_id": photo_url}).eq("master_id", master_id).execute()


async def get_masters_by_category(category: str) -> list[dict]:
    db = await _db()
    res = await db.table("bot_masters").select("*").eq("category", category).eq("is_active", 1).execute()
    return res.data or []


async def get_master(master_id: str) -> dict | None:
    db = await _db()
    res = await db.table("bot_masters").select("*").eq("master_id", master_id).maybe_single().execute()
    return res.data


async def set_master_telegram_id(master_id: str, telegram_user_id: int | None) -> None:
    db = await _db()
    await db.table("bot_masters").update({"telegram_user_id": telegram_user_id}).eq("master_id", master_id).execute()


async def get_master_by_telegram_id(telegram_user_id: int) -> dict | None:
    db = await _db()
    res = await db.table("bot_masters").select("*").eq("telegram_user_id", telegram_user_id).maybe_single().execute()
    return res.data


async def set_master_photo(master_id: str, photo_file_id: str) -> None:
    db = await _db()
    await db.table("bot_masters").update({"photo_file_id": photo_file_id}).eq("master_id", master_id).execute()


async def get_master_photo(master_id: str) -> str | None:
    db = await _db()
    res = await db.table("bot_masters").select("photo_file_id").eq("master_id", master_id).maybe_single().execute()
    return res.data["photo_file_id"] if res.data else None


async def get_all_masters_with_photos() -> list[dict]:
    db = await _db()
    res = await db.table("bot_masters").select("master_id,name,category,photo_file_id").eq("is_active", 1).order("category").order("name").execute()
    return res.data or []


async def get_all_masters_admin() -> list[dict]:
    db = await _db()
    res = await db.table("bot_masters").select("*").order("category").order("name").execute()
    return res.data or []


async def add_master_to_db(master_id: str, name: str, category: str,
                            description: str = "", telegram_user_id: int = None) -> None:
    db = await _db()
    try:
        await db.table("bot_masters").insert({
            "master_id": master_id, "name": name, "category": category,
            "description": description, "telegram_user_id": telegram_user_id, "is_active": 1,
        }).execute()
    except Exception:
        pass


async def update_master_name(master_id: str, name: str) -> None:
    db = await _db()
    await db.table("bot_masters").update({"name": name}).eq("master_id", master_id).execute()


async def update_master_description(master_id: str, description: str) -> None:
    db = await _db()
    await db.table("bot_masters").update({"description": description}).eq("master_id", master_id).execute()


async def toggle_master_active(master_id: str) -> int:
    db = await _db()
    res = await db.table("bot_masters").select("is_active").eq("master_id", master_id).maybe_single().execute()
    current = res.data["is_active"] if res.data else 1
    new_val = 0 if current else 1
    await db.table("bot_masters").update({"is_active": new_val}).eq("master_id", master_id).execute()
    return new_val


# ════════════════════════════════════════════════════════
#  Администраторы
# ════════════════════════════════════════════════════════

async def get_all_admins() -> list[dict]:
    db = await _db()
    res = await db.table("bot_admins").select("*").order("created_at").execute()
    return res.data or []


async def add_admin(user_id: int, username: str, full_name: str, added_by: int) -> None:
    db = await _db()
    await db.table("bot_admins").upsert({
        "user_id": user_id, "username": username or "",
        "full_name": full_name or "", "added_by": added_by,
    }).execute()


async def remove_admin(user_id: int) -> None:
    db = await _db()
    await db.table("bot_admins").delete().eq("user_id", user_id).execute()


async def is_admin_in_db(user_id: int) -> bool:
    db = await _db()
    res = await db.table("bot_admins").select("user_id").eq("user_id", user_id).maybe_single().execute()
    return res.data is not None


async def get_user_by_username(username: str) -> dict | None:
    db = await _db()
    clean = username.lstrip("@").lower()
    res = await db.table("bot_users").select("*").ilike("username", clean).maybe_single().execute()
    return res.data


# ════════════════════════════════════════════════════════
#  Лояльность и дни рождения
# ════════════════════════════════════════════════════════

async def increment_visit_count(user_id: int) -> int:
    user = await get_user(user_id)
    current = (user or {}).get("visit_count", 0) or 0
    new_val = current + 1
    db = await _db()
    await db.table("bot_users").update({"visit_count": new_val}).eq("user_id", user_id).execute()
    return new_val


async def get_user_visit_count(user_id: int) -> int:
    user = await get_user(user_id)
    return (user or {}).get("visit_count", 0) or 0


async def update_user_birthdate(user_id: int, birthdate: str) -> None:
    db = await _db()
    await db.table("bot_users").update({"birthdate": birthdate}).eq("user_id", user_id).execute()


async def get_birthday_users_today() -> list[dict]:
    from datetime import date
    today_mmdd = date.today().strftime("%m-%d")
    db = await _db()
    res = await db.table("bot_users").select("*").eq("birthdate", today_mmdd).execute()
    return res.data or []


# ════════════════════════════════════════════════════════
#  Отзывы
# ════════════════════════════════════════════════════════

async def create_review(booking_id: int, user_id: int, master_id: str,
                        rating: int, comment: str = "") -> int:
    db = await _db()
    res = await db.table("bot_reviews").upsert({
        "booking_id": booking_id, "user_id": user_id,
        "master_id": master_id, "rating": rating, "comment": comment,
    }, on_conflict="booking_id").execute()
    return res.data[0]["id"] if res.data else 0


async def get_review_by_booking(booking_id: int) -> dict | None:
    db = await _db()
    res = await db.table("bot_reviews").select("*").eq("booking_id", booking_id).maybe_single().execute()
    return res.data


async def get_master_reviews(master_id: str, limit: int = 20) -> list[dict]:
    db = await _db()
    res = await db.table("bot_reviews").select("*").eq("master_id", master_id).order("created_at", desc=True).limit(limit).execute()
    return res.data or []


async def get_avg_rating(master_id: str) -> float | None:
    db = await _db()
    res = await db.table("bot_reviews").select("rating").eq("master_id", master_id).execute()
    ratings = [r["rating"] for r in (res.data or []) if r["rating"] is not None]
    return round(sum(ratings) / len(ratings), 1) if ratings else None


async def get_bookings_for_review() -> list[dict]:
    from datetime import date, timedelta
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    db = await _db()
    res = await (db.table("bot_bookings")
                 .select("*")
                 .eq("date", yesterday)
                 .eq("status", "confirmed")
                 .eq("review_requested", 0)
                 .execute())
    return res.data or []


async def mark_review_requested(booking_id: int) -> None:
    db = await _db()
    await db.table("bot_bookings").update({"review_requested": 1}).eq("id", booking_id).execute()


# ════════════════════════════════════════════════════════
#  Галерея работ
# ════════════════════════════════════════════════════════

async def add_gallery_photo(master_id: str, category: str, file_id: str, caption: str = "") -> int:
    db = await _db()
    res = await db.table("bot_gallery").insert({
        "master_id": master_id, "category": category, "file_id": file_id, "caption": caption,
    }).execute()
    return res.data[0]["id"] if res.data else 0


async def get_gallery_by_category(category: str, limit: int = 20) -> list[dict]:
    db = await _db()
    res = await db.table("bot_gallery").select("*").eq("category", category).order("created_at", desc=True).limit(limit).execute()
    return res.data or []


async def get_all_gallery(limit: int = 50) -> list[dict]:
    db = await _db()
    res = await db.table("bot_gallery").select("*").order("created_at", desc=True).limit(limit).execute()
    return res.data or []


async def delete_gallery_photo(photo_id: int) -> None:
    db = await _db()
    await db.table("bot_gallery").delete().eq("id", photo_id).execute()


# ════════════════════════════════════════════════════════
#  Заметки мастера о клиентах
# ════════════════════════════════════════════════════════

async def save_client_note(master_id: str, client_user_id: int, note: str) -> None:
    db = await _db()
    await db.table("bot_client_notes").upsert({
        "master_id": master_id, "client_user_id": client_user_id, "note": note,
    }, on_conflict="master_id,client_user_id").execute()


async def get_client_note(master_id: str, client_user_id: int) -> str | None:
    db = await _db()
    res = await (db.table("bot_client_notes")
                 .select("note")
                 .eq("master_id", master_id)
                 .eq("client_user_id", client_user_id)
                 .maybe_single().execute())
    return res.data["note"] if res.data else None


# ════════════════════════════════════════════════════════
#  Рассылка
# ════════════════════════════════════════════════════════

async def get_all_user_ids() -> list[int]:
    db = await _db()
    res = await db.table("bot_users").select("user_id").execute()
    return [r["user_id"] for r in (res.data or [])]


# ════════════════════════════════════════════════════════
#  Настройки салона
# ════════════════════════════════════════════════════════

_settings_cache: dict = {}


async def seed_salon_settings() -> None:
    from data.salon import (
        SALON_NAME, SALON_ADDRESS, SALON_METRO, SALON_PHONE,
        SALON_INSTAGRAM, SALON_SINCE, SALON_HOURS,
    )
    defaults = {
        "salon_name":           SALON_NAME,
        "salon_address":        SALON_ADDRESS,
        "salon_metro":          SALON_METRO,
        "salon_phone":          SALON_PHONE,
        "salon_instagram":      SALON_INSTAGRAM,
        "salon_since":          SALON_SINCE,
        "salon_hours_weekdays": SALON_HOURS["weekdays"],
        "salon_hours_weekends": SALON_HOURS["weekends"],
        "currency":             "€",
        "specialist_label":     "мастер",
        "specialists_label":    "Специалисты",
        "photo_main": "", "photo_services": "", "photo_masters": "",
        "photo_booking": "", "photo_about": "", "photo_admin": "",
    }
    db = await _db()
    rows = [{"key": k, "value": v} for k, v in defaults.items()]
    existing = await db.table("bot_salon_settings").select("key").execute()
    existing_keys = {r["key"] for r in (existing.data or [])}
    new_rows = [r for r in rows if r["key"] not in existing_keys]
    if new_rows:
        await db.table("bot_salon_settings").insert(new_rows).execute()
    await _refresh_settings()


async def _refresh_settings() -> None:
    db = await _db()
    res = await db.table("bot_salon_settings").select("key,value").execute()
    _settings_cache.clear()
    for row in (res.data or []):
        _settings_cache[row["key"]] = row["value"]


async def get_setting(key: str, default: str = "") -> str:
    if not _settings_cache:
        await _refresh_settings()
    return _settings_cache.get(key, default)


async def set_setting(key: str, value: str) -> None:
    db = await _db()
    await db.table("bot_salon_settings").upsert({"key": key, "value": value}).execute()
    _settings_cache[key] = value


async def get_all_settings() -> dict:
    if not _settings_cache:
        await _refresh_settings()
    return dict(_settings_cache)


async def get_system_lang() -> str:
    return await get_setting("default_lang", "ru")


# ════════════════════════════════════════════════════════
#  GDPR
# ════════════════════════════════════════════════════════

async def mark_gdpr_accepted(user_id: int) -> None:
    db = await _db()
    await db.table("bot_users").update({"gdpr_accepted": 1}).eq("user_id", user_id).execute()


async def delete_user_data(user_id: int) -> None:
    db = await _db()
    await db.table("bot_users").update({
        "username": "[deleted]", "full_name": "[deleted]",
        "phone": None, "birthdate": None, "gdpr_accepted": 0,
    }).eq("user_id", user_id).execute()
    await db.table("bot_bookings").update({
        "user_name": "[deleted]", "username": "[deleted]", "phone": "[deleted]",
    }).eq("user_id", user_id).execute()


# ════════════════════════════════════════════════════════
#  Кастомные слоты мастера
# ════════════════════════════════════════════════════════

async def add_master_custom_slot(master_id: str, date: str, time_start: str) -> bool:
    db = await _db()
    try:
        await db.table("bot_master_custom_slots").insert({
            "master_id": master_id, "date": date, "time_start": time_start,
        }).execute()
        return True
    except Exception:
        return False


async def get_master_custom_slots(master_id: str, date: str) -> list[dict]:
    db = await _db()
    res = await (db.table("bot_master_custom_slots")
                 .select("*")
                 .eq("master_id", master_id)
                 .eq("date", date)
                 .order("time_start").execute())
    return res.data or []


async def has_master_custom_slots(master_id: str, date: str) -> bool:
    db = await _db()
    res = await (db.table("bot_master_custom_slots")
                 .select("id", count="exact")
                 .eq("master_id", master_id)
                 .eq("date", date).execute())
    return (res.count or 0) > 0


async def delete_master_custom_slot(slot_id: int) -> None:
    db = await _db()
    await db.table("bot_master_custom_slots").delete().eq("id", slot_id).execute()


async def clear_master_custom_slots(master_id: str, date: str) -> None:
    booked = await get_booked_slots(master_id, date)
    booked_times = {s["time_start"] for s in booked}
    slots = await get_master_custom_slots(master_id, date)
    db = await _db()
    for slot in slots:
        if slot["time_start"] not in booked_times:
            await db.table("bot_master_custom_slots").delete().eq("id", slot["id"]).execute()


# ════════════════════════════════════════════════════════
#  Категории и услуги
# ════════════════════════════════════════════════════════

async def seed_services() -> None:
    from data.salon import SERVICES
    db = await _db()
    cat_rows = []
    svc_rows = []
    for sort_i, (cat_key, cat) in enumerate(SERVICES.items()):
        cat_rows.append({"cat_key": cat_key, "title": cat["title"], "sort_order": sort_i})
        for svc_sort, item in enumerate(cat["items"]):
            svc_rows.append({
                "service_id": item["id"], "category": cat_key, "name": item["name"],
                "price": item["price"], "duration": item["duration"], "sort_order": svc_sort,
            })
    if cat_rows:
        await db.table("bot_service_categories").upsert(cat_rows, on_conflict="cat_key").execute()
    if svc_rows:
        await db.table("bot_services").upsert(svc_rows, on_conflict="service_id").execute()
    logger.info("Услуги синхронизированы с Supabase")


async def get_categories() -> list[dict]:
    db = await _db()
    res = await db.table("bot_service_categories").select("*").eq("is_active", 1).order("sort_order").order("cat_key").execute()
    return res.data or []


async def get_category_by_key(cat_key: str) -> dict | None:
    db = await _db()
    res = await db.table("bot_service_categories").select("*").eq("cat_key", cat_key).maybe_single().execute()
    return res.data


async def get_db_services_by_category(category: str) -> list[dict]:
    db = await _db()
    res = await db.table("bot_services").select("*").eq("category", category).eq("is_active", 1).order("sort_order").order("id").execute()
    return res.data or []


async def get_db_service_by_id(service_id: str) -> dict | None:
    db = await _db()
    res = await db.table("bot_services").select("*").eq("service_id", service_id).maybe_single().execute()
    return res.data


async def get_all_services_admin() -> list[dict]:
    db = await _db()
    res = await db.table("bot_services").select("*").order("category").order("sort_order").order("id").execute()
    return res.data or []


async def add_db_service(service_id: str, category: str, name: str,
                         price: int, duration: int) -> None:
    db = await _db()
    await db.table("bot_services").insert({
        "service_id": service_id, "category": category,
        "name": name, "price": price, "duration": duration,
    }).execute()


async def update_db_service(service_id: str, **kwargs) -> None:
    allowed = {"name", "price", "duration", "sort_order", "is_active", "category"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    db = await _db()
    await db.table("bot_services").update(updates).eq("service_id", service_id).execute()


async def delete_db_service(service_id: str) -> None:
    db = await _db()
    await db.table("bot_services").delete().eq("service_id", service_id).execute()


async def add_db_category(cat_key: str, title: str) -> None:
    db = await _db()
    try:
        await db.table("bot_service_categories").insert({"cat_key": cat_key, "title": title}).execute()
    except Exception:
        pass


async def update_db_category(cat_key: str, **kwargs) -> None:
    allowed = {"title", "sort_order", "is_active"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    db = await _db()
    await db.table("bot_service_categories").update(updates).eq("cat_key", cat_key).execute()


async def get_specialist_label() -> str:
    return await get_setting("specialist_label", "мастер")


async def get_specialists_label() -> str:
    return await get_setting("specialists_label", "Специалисты")


# ════════════════════════════════════════════════════════
#  Лог действий
# ════════════════════════════════════════════════════════

async def log_action(user_id: int, action: str, target: str = "",
                     status: str = "ok", details: str = "") -> None:
    try:
        db = await _db()
        await db.table("bot_audit_log").insert({
            "user_id": user_id, "action": action,
            "target": target, "status": status, "details": details,
        }).execute()
    except Exception as e:
        logger.error(f"log_action failed: {e}")


async def get_audit_log(limit: int = 50) -> list[dict]:
    db = await _db()
    res = await db.table("bot_audit_log").select("*").order("id", desc=True).limit(limit).execute()
    return res.data or []


# ════════════════════════════════════════════════════════
#  Статистика за период
# ════════════════════════════════════════════════════════

async def get_period_stats(days: int) -> dict:
    from datetime import date, timedelta
    since = (date.today() - timedelta(days=days)).isoformat()
    db = await _db()

    res = await db.table("bot_bookings").select("id", count="exact").gte("date", since).execute()
    bookings_total = res.count or 0

    res = await db.table("bot_bookings").select("id", count="exact").gte("date", since).eq("status", "confirmed").execute()
    bookings_confirmed = res.count or 0

    res = await db.table("bot_users").select("user_id", count="exact").gte("created_at", since).execute()
    new_clients = res.count or 0

    res = await db.table("bot_bookings").select("service").gte("date", since).execute()
    from collections import Counter
    svc_counter = Counter(r["service"] for r in (res.data or []) if r["service"])
    top_services = [{"service": s, "cnt": c} for s, c in svc_counter.most_common(5)]

    res = await db.table("bot_bookings").select("master").gte("date", since).execute()
    master_counter = Counter(r["master"] for r in (res.data or []) if r["master"])
    top_masters = [{"master": m, "cnt": c} for m, c in master_counter.most_common(5)]

    res = await db.table("bot_reviews").select("rating").execute()
    ratings = [r["rating"] for r in (res.data or []) if r["rating"] is not None]
    avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else None

    return {
        "days": days,
        "bookings_total": bookings_total,
        "bookings_confirmed": bookings_confirmed,
        "new_clients": new_clients,
        "top_services": top_services,
        "top_masters": top_masters,
        "avg_rating": avg_rating,
    }
