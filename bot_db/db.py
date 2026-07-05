"""
Все операции с базой данных — только здесь.
Используем aiosqlite для асинхронной работы.
"""

import aiosqlite
import logging
from config import DB_PATH

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════
#  Инициализация БД
# ══════════════════════════════════════════════════════════

async def init_db() -> None:
    """Создать таблицы если не существуют. Вызывается при старте бота."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                full_name   TEXT,
                lang        TEXT    DEFAULT 'ru',
                last_msg_id INTEGER DEFAULT NULL,
                created_at  TEXT    DEFAULT (datetime('now'))
            )
        """)
        # Миграция: добавить колонку если БД уже существует
        try:
            await db.execute("ALTER TABLE users ADD COLUMN last_msg_id INTEGER DEFAULT NULL")
        except Exception:
            pass  # колонка уже есть
        try:
            await db.execute("ALTER TABLE users ADD COLUMN phone TEXT DEFAULT NULL")
        except Exception:
            pass  # колонка уже есть
        try:
            await db.execute("ALTER TABLE users ADD COLUMN last_photo_msg_id INTEGER DEFAULT NULL")
        except Exception:
            pass  # колонка уже есть
        # ── Записи на приём ───────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER,
                user_name   TEXT,
                username    TEXT,
                service     TEXT,
                service_id  TEXT,
                master      TEXT,
                master_id   TEXT,
                date        TEXT,
                time_start  TEXT,
                duration    INTEGER,
                date_time   TEXT,
                phone       TEXT,
                status      TEXT DEFAULT 'new',
                created_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        # Миграция: добавить новые колонки если БД уже существует
        for col_def in [
            "ALTER TABLE bookings ADD COLUMN username TEXT",
            "ALTER TABLE bookings ADD COLUMN service_id TEXT",
            "ALTER TABLE bookings ADD COLUMN master_id TEXT",
            "ALTER TABLE bookings ADD COLUMN date TEXT",
            "ALTER TABLE bookings ADD COLUMN time_start TEXT",
            "ALTER TABLE bookings ADD COLUMN duration INTEGER",
        ]:
            try:
                await db.execute(col_def)
            except Exception:
                pass  # колонка уже есть
        # ── Расписание мастеров ───────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS master_schedules (
                master_id   TEXT,
                day_of_week INTEGER,
                start_time  TEXT,
                end_time    TEXT,
                is_working  INTEGER DEFAULT 1,
                PRIMARY KEY (master_id, day_of_week)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS master_dayoffs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                master_id   TEXT,
                date        TEXT,
                reason      TEXT DEFAULT '',
                created_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        # ── Мастера (профили) ─────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS masters (
                master_id        TEXT PRIMARY KEY,
                name             TEXT,
                category         TEXT,
                description      TEXT DEFAULT '',
                telegram_user_id INTEGER DEFAULT NULL,
                is_active        INTEGER DEFAULT 1
            )
        """)
        # Миграция: добавить колонку photo_file_id
        try:
            await db.execute("ALTER TABLE masters ADD COLUMN photo_file_id TEXT DEFAULT NULL")
        except Exception:
            pass  # колонка уже есть
        # ── Администраторы ────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id    INTEGER PRIMARY KEY,
                username   TEXT DEFAULT '',
                full_name  TEXT DEFAULT '',
                added_by   INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        # ── Расширение пользователей (лояльность + дни рождения) ──
        for col_def in [
            "ALTER TABLE users ADD COLUMN visit_count INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN birthdate TEXT DEFAULT NULL",
        ]:
            try:
                await db.execute(col_def)
            except Exception:
                pass
        # ── Расширение записей (посещаемость + запрос отзыва) ──
        for col_def in [
            "ALTER TABLE bookings ADD COLUMN attended INTEGER DEFAULT NULL",
            "ALTER TABLE bookings ADD COLUMN review_requested INTEGER DEFAULT 0",
        ]:
            try:
                await db.execute(col_def)
            except Exception:
                pass
        # ── Отзывы ───────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_id  INTEGER UNIQUE,
                user_id     INTEGER,
                master_id   TEXT,
                rating      INTEGER,
                comment     TEXT DEFAULT '',
                created_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        # ── Галерея работ ─────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS gallery (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                master_id   TEXT DEFAULT '',
                category    TEXT DEFAULT '',
                file_id     TEXT,
                caption     TEXT DEFAULT '',
                created_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        # ── Заметки мастера о клиентах ────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS client_notes (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                master_id       TEXT,
                client_user_id  INTEGER,
                note            TEXT DEFAULT '',
                updated_at      TEXT DEFAULT (datetime('now')),
                UNIQUE(master_id, client_user_id)
            )
        """)
        # ── GDPR согласие ─────────────────────────────────
        try:
            await db.execute("ALTER TABLE users ADD COLUMN gdpr_accepted INTEGER DEFAULT 0")
        except Exception:
            pass
        # ── Настройки салона ──────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS salon_settings (
                key        TEXT PRIMARY KEY,
                value      TEXT DEFAULT ''
            )
        """)
        # ── Кастомные слоты мастера на день ───────────────
        # Если для даты есть хотя бы один кастомный слот,
        # автогенерация НЕ используется — только эти слоты.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS master_custom_slots (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                master_id   TEXT,
                date        TEXT,
                time_start  TEXT,
                created_at  TEXT DEFAULT (datetime('now')),
                UNIQUE(master_id, date, time_start)
            )
        """)
        # ── Лог действий ──────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at  TEXT DEFAULT (datetime('now', 'localtime')),
                user_id     INTEGER,
                action      TEXT,
                target      TEXT DEFAULT '',
                status      TEXT DEFAULT 'ok',
                details     TEXT DEFAULT ''
            )
        """)
        # ── Категории услуг ───────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS service_categories (
                cat_key     TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                sort_order  INTEGER DEFAULT 0,
                is_active   INTEGER DEFAULT 1
            )
        """)
        # ── Услуги ────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS services (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                service_id  TEXT UNIQUE NOT NULL,
                category    TEXT NOT NULL,
                name        TEXT NOT NULL,
                price       INTEGER NOT NULL DEFAULT 0,
                duration    INTEGER NOT NULL DEFAULT 60,
                sort_order  INTEGER DEFAULT 0,
                is_active   INTEGER DEFAULT 1
            )
        """)
        await db.commit()
    logger.info("База данных инициализирована")
    await seed_master_schedules()
    await seed_masters()
    await seed_master_photos()
    await seed_salon_settings()
    await seed_services()


# ══════════════════════════════════════════════════════════
#  Пользователи
# ══════════════════════════════════════════════════════════

async def get_user(user_id: int) -> dict | None:
    """Получить пользователя по ID. Возвращает dict или None."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def register_user(user_id: int, username: str, full_name: str, lang: str) -> None:
    """Зарегистрировать нового пользователя (INSERT OR IGNORE)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO users (user_id, username, full_name, lang)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, username, full_name, lang),
        )
        await db.commit()


async def update_user_lang(user_id: int, lang: str) -> None:
    """Обновить язык пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET lang = ? WHERE user_id = ?",
            (lang, user_id),
        )
        await db.commit()


async def get_user_lang(user_id: int) -> str:
    """Быстро получить язык пользователя."""
    user = await get_user(user_id)
    return user["lang"] if user else "ru"


async def update_user_name(user_id: int, full_name: str) -> None:
    """Обновить имя пользователя (после регистрации)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET full_name = ? WHERE user_id = ?",
            (full_name, user_id),
        )
        await db.commit()


async def update_user_phone(user_id: int, phone: str) -> None:
    """Сохранить телефон пользователя для будущих записей."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET phone = ? WHERE user_id = ?",
            (phone, user_id),
        )
        await db.commit()


async def get_user_phone(user_id: int) -> str | None:
    """Получить сохранённый телефон пользователя."""
    user = await get_user(user_id)
    return user.get("phone") if user else None


# ══════════════════════════════════════════════════════════
#  Последнее сообщение бота (для чистого UX — одно окно)
# ══════════════════════════════════════════════════════════

async def get_last_photo_msg_id(user_id: int) -> int | None:
    """Получить ID последнего фото-сообщения бота."""
    user = await get_user(user_id)
    return user.get("last_photo_msg_id") if user else None


async def save_last_photo_msg_id(user_id: int, msg_id: int) -> None:
    """Сохранить ID последнего фото-сообщения бота."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET last_photo_msg_id = ? WHERE user_id = ?",
            (msg_id, user_id),
        )
        await db.commit()


async def get_last_msg_id(user_id: int) -> int | None:
    """Получить ID последнего сообщения бота для этого пользователя."""
    user = await get_user(user_id)
    return user["last_msg_id"] if user else None


async def save_last_msg_id(user_id: int, msg_id: int) -> None:
    """Сохранить ID последнего сообщения бота."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET last_msg_id = ? WHERE user_id = ?",
            (msg_id, user_id),
        )
        await db.commit()


# ══════════════════════════════════════════════════════════
#  Статистика (для админ-панели)
# ══════════════════════════════════════════════════════════

async def get_users_count() -> int:
    """Общее количество пользователей."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def get_today_users_count() -> int:
    """Количество новых пользователей за сегодня (по UTC)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM users WHERE date(created_at) = date('now')"
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def get_last_user() -> dict | None:
    """Последний зарегистрированный пользователь."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users ORDER BY created_at DESC LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_recent_users(limit: int = 10) -> list[dict]:
    """Список последних N пользователей (по дате регистрации)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users ORDER BY created_at DESC LIMIT ?", (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


# ══════════════════════════════════════════════════════════
#  Записи на приём (bookings)
# ══════════════════════════════════════════════════════════

async def create_booking(
    user_id: int,
    user_name: str,
    username: str,
    service: str,
    service_id: str,
    master: str,
    master_id: str,
    date: str,
    time_start: str,
    duration: int,
    phone: str,
) -> int | None:
    """
    Атомарно создать запись на приём.
    Возвращает id созданной записи или None если слот уже занят (race condition).
    """
    date_time = f"{date} {time_start}" if date and time_start else ""
    async with aiosqlite.connect(DB_PATH) as db:
        # ── Финальная проверка свободности слота ──────────
        # Считаем записи, которые пересекаются с [time_start, time_start+duration)
        # Используем строковое сравнение HH:MM — работает корректно для формата
        async with db.execute(
            """SELECT COUNT(*) FROM bookings
               WHERE master_id = ? AND date = ?
               AND status NOT IN ('cancelled','rejected')
               AND time_start < ?
               AND (
                   CASE WHEN length(time_start)=5
                   THEN printf('%02d:%02d',
                       (CAST(substr(time_start,1,2) AS INT)*60 + CAST(substr(time_start,4,2) AS INT) + duration) / 60,
                       (CAST(substr(time_start,1,2) AS INT)*60 + CAST(substr(time_start,4,2) AS INT) + duration) % 60)
                   ELSE '99:99' END
               ) > ?""",
            (master_id, date,
             # existing.time_start < new_slot_end
             _add_minutes_str(time_start, duration),
             # existing.time_start + existing.duration > new_slot_start
             time_start)
        ) as cur:
            count = (await cur.fetchone())[0]

        if count > 0:
            logger.warning(
                "Слот занят (race condition): master=%s date=%s time=%s",
                master_id, date, time_start
            )
            return None

        cursor = await db.execute(
            """
            INSERT INTO bookings
              (user_id, user_name, username, service, service_id,
               master, master_id, date, time_start, duration, date_time, phone)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, user_name, username, service, service_id,
             master, master_id, date, time_start, duration, date_time, phone),
        )
        await db.commit()
        return cursor.lastrowid


def _add_minutes_str(time_str: str, minutes: int) -> str:
    """'HH:MM' + N минут → 'HH:MM'."""
    h, m = map(int, time_str.split(":"))
    total = h * 60 + m + minutes
    return f"{total // 60:02d}:{total % 60:02d}"


async def get_booked_slots(master_id: str, date_str: str) -> list[dict]:
    """Все записи мастера на дату (кроме cancelled)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT time_start, duration FROM bookings
               WHERE master_id = ? AND date = ? AND status != 'cancelled'""",
            (master_id, date_str)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_user_bookings(user_id: int) -> list[dict]:
    """Все записи конкретного пользователя (сначала новые)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM bookings WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_all_bookings(limit: int = 20) -> list[dict]:
    """Последние N записей (для админа)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM bookings ORDER BY created_at DESC LIMIT ?", (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_pending_bookings_count() -> int:
    """Количество записей со статусом 'new'."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM bookings WHERE status = 'new'") as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def get_pending_bookings(limit: int = 10) -> list[dict]:
    """Записи ожидающие подтверждения (status='new'), новые первые."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM bookings WHERE status = 'new' ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_bookings_for_tomorrow() -> list[dict]:
    """Все активные записи на завтра (для напоминаний клиентам)."""
    from datetime import date, timedelta
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT b.*, u.last_msg_id FROM bookings b
               LEFT JOIN users u ON b.user_id = u.user_id
               WHERE b.date = ? AND b.status NOT IN ('cancelled','rejected')
               ORDER BY b.time_start ASC""",
            (tomorrow,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_upcoming_bookings_for_master(master_id: str, limit: int = 10) -> list[dict]:
    """Предстоящие записи мастера (сегодня и позже, не отменённые)."""
    from datetime import date as _date
    today = _date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM bookings
               WHERE master_id = ? AND date >= ? AND status NOT IN ('cancelled','rejected')
               ORDER BY date ASC, time_start ASC LIMIT ?""",
            (master_id, today, limit)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_all_users_paginated(limit: int = 20, offset: int = 0) -> list[dict]:
    """Пользователи с пагинацией для панели администратора."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_users_total_count() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def get_bookings_count() -> int:
    """Общее количество записей."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM bookings") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def get_today_bookings_count() -> int:
    """Количество записей за сегодня."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM bookings WHERE date(created_at) = date('now')"
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def get_booking(booking_id: int) -> dict | None:
    """Получить запись на приём по ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM bookings WHERE id = ?", (booking_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def update_booking_status(booking_id: int, status: str) -> None:
    """Обновить статус записи: new / confirmed / cancelled."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE bookings SET status = ? WHERE id = ?",
            (status, booking_id),
        )
        await db.commit()


# ══════════════════════════════════════════════════════════
#  Расписание мастеров
# ══════════════════════════════════════════════════════════

async def seed_master_schedules() -> None:
    """Заполняет master_schedules из salon.py если таблица пустая."""
    from data.salon import MASTER_SCHEDULE
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM master_schedules") as cur:
            count = (await cur.fetchone())[0]
        if count > 0:
            return
        for master_id, info in MASTER_SCHEDULE.items():
            for day in range(7):
                is_working = 1 if day in info["working_days"] else 0
                await db.execute(
                    """INSERT OR IGNORE INTO master_schedules
                       (master_id, day_of_week, start_time, end_time, is_working)
                       VALUES (?, ?, ?, ?, ?)""",
                    (master_id, day, info["start"], info["end"], is_working)
                )
        await db.commit()
    logger.info("Расписание мастеров перенесено в БД")


async def get_master_schedule(master_id: str) -> list[dict]:
    """Расписание мастера — 7 строк (по одной на день)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM master_schedules WHERE master_id = ? ORDER BY day_of_week",
            (master_id,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def toggle_master_day(master_id: str, day_of_week: int) -> int:
    """Переключить рабочий/выходной для дня. Возвращает новое значение is_working."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT is_working FROM master_schedules WHERE master_id=? AND day_of_week=?",
            (master_id, day_of_week)
        ) as cur:
            row = await cur.fetchone()
        new_val = 0 if (row and row[0]) else 1
        await db.execute(
            "UPDATE master_schedules SET is_working=? WHERE master_id=? AND day_of_week=?",
            (new_val, master_id, day_of_week)
        )
        await db.commit()
        return new_val


async def update_master_hours(master_id: str, day_of_week: int, start: str, end: str) -> None:
    """Обновить часы работы мастера для конкретного дня."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE master_schedules SET start_time=?, end_time=? WHERE master_id=? AND day_of_week=?",
            (start, end, master_id, day_of_week)
        )
        await db.commit()


async def update_master_all_hours(master_id: str, start: str, end: str) -> None:
    """Обновить часы работы мастера для всех рабочих дней сразу."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE master_schedules SET start_time=?, end_time=? WHERE master_id=? AND is_working=1",
            (start, end, master_id)
        )
        await db.commit()


async def add_master_dayoff(master_id: str, date: str, reason: str = "") -> None:
    """Добавить выходной день мастера."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO master_dayoffs (master_id, date, reason) VALUES (?,?,?)",
            (master_id, date, reason)
        )
        await db.commit()


async def get_master_dayoffs(master_id: str) -> list[dict]:
    """Будущие выходные мастера."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM master_dayoffs WHERE master_id=? AND date >= date('now') ORDER BY date",
            (master_id,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def delete_master_dayoff(dayoff_id: int) -> None:
    """Удалить выходной день мастера по ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM master_dayoffs WHERE id=?", (dayoff_id,))
        await db.commit()


# ══════════════════════════════════════════════════════════
#  Профили мастеров
# ══════════════════════════════════════════════════════════

async def seed_masters() -> None:
    """Заполняет таблицу masters из salon.py если она пустая."""
    from data.salon import MASTER_SCHEDULE
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM masters") as cur:
            if (await cur.fetchone())[0] > 0:
                return
        for master_id, info in MASTER_SCHEDULE.items():
            await db.execute(
                "INSERT OR IGNORE INTO masters (master_id, name, category) VALUES (?,?,?)",
                (master_id, info["name"], info["category"])
            )
        await db.commit()
    logger.info("Профили мастеров перенесены в БД")


async def seed_master_photos() -> None:
    """Заполняет photo_file_id из MASTER_PHOTOS если не задан."""
    from data.salon import MASTER_PHOTOS
    async with aiosqlite.connect(DB_PATH) as db:
        for master_id, photo_url in MASTER_PHOTOS.items():
            await db.execute(
                "UPDATE masters SET photo_file_id = ? WHERE master_id = ? AND (photo_file_id IS NULL OR photo_file_id = '')",
                (photo_url, master_id)
            )
        await db.commit()


async def get_masters_by_category(category: str) -> list[dict]:
    """Список активных мастеров категории."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM masters WHERE category = ? AND is_active = 1",
            (category,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_master(master_id: str) -> dict | None:
    """Получить мастера по master_id."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM masters WHERE master_id = ?", (master_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def set_master_telegram_id(master_id: str, telegram_user_id: int | None) -> None:
    """Привязать или отвязать Telegram-аккаунт от мастера (None = отвязать)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE masters SET telegram_user_id = ? WHERE master_id = ?",
            (telegram_user_id, master_id)
        )
        await db.commit()


async def get_master_by_telegram_id(telegram_user_id: int) -> dict | None:
    """Найти мастера по Telegram user_id."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM masters WHERE telegram_user_id = ?", (telegram_user_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


# ══════════════════════════════════════════════════════════
#  Фото мастеров
# ══════════════════════════════════════════════════════════

async def set_master_photo(master_id: str, photo_file_id: str) -> None:
    """Установить фото мастера."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE masters SET photo_file_id = ? WHERE master_id = ?",
            (photo_file_id, master_id)
        )
        await db.commit()


async def get_master_photo(master_id: str) -> str | None:
    """Получить file_id фото мастера или None."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT photo_file_id FROM masters WHERE master_id = ?", (master_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


async def get_all_masters_with_photos() -> list[dict]:
    """Все активные мастера с полями master_id, name, category, photo_file_id."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT master_id, name, category, photo_file_id FROM masters WHERE is_active = 1 ORDER BY category, name"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ══════════════════════════════════════════════════════════
#  Администраторы
# ══════════════════════════════════════════════════════════

async def get_all_admins() -> list[dict]:
    """Список всех дополнительных администраторов."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM admins ORDER BY created_at"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def add_admin(user_id: int, username: str, full_name: str, added_by: int) -> None:
    """Добавить администратора в таблицу admins."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR REPLACE INTO admins (user_id, username, full_name, added_by)
               VALUES (?, ?, ?, ?)""",
            (user_id, username or '', full_name or '', added_by)
        )
        await db.commit()


async def remove_admin(user_id: int) -> None:
    """Удалить администратора из таблицы admins."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
        await db.commit()


async def is_admin_in_db(user_id: int) -> bool:
    """Проверить наличие user_id в таблице admins."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM admins WHERE user_id = ?", (user_id,)
        ) as cur:
            return await cur.fetchone() is not None


async def get_user_by_username(username: str) -> dict | None:
    """Найти пользователя по username (без @)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (username.lstrip("@"),)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_all_masters_admin() -> list[dict]:
    """Все мастера включая неактивных — для панели администратора."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM masters ORDER BY category, name"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def add_master_to_db(master_id: str, name: str, category: str,
                            description: str = "", telegram_user_id: int = None) -> None:
    """Добавить нового мастера в БД."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR IGNORE INTO masters
               (master_id, name, category, description, telegram_user_id, is_active)
               VALUES (?, ?, ?, ?, ?, 1)""",
            (master_id, name, category, description, telegram_user_id)
        )
        await db.commit()


async def update_master_name(master_id: str, name: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE masters SET name = ? WHERE master_id = ?", (name, master_id))
        await db.commit()


async def update_master_description(master_id: str, description: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE masters SET description = ? WHERE master_id = ?", (description, master_id))
        await db.commit()


async def toggle_master_active(master_id: str) -> int:
    """Переключить активность мастера. Возвращает новое значение (0 или 1)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT is_active FROM masters WHERE master_id = ?", (master_id,)) as cur:
            row = await cur.fetchone()
            current = row[0] if row else 1
        new_val = 0 if current else 1
        await db.execute("UPDATE masters SET is_active = ? WHERE master_id = ?", (new_val, master_id))
        await db.commit()
        return new_val


# ══════════════════════════════════════════════════════════
#  Лояльность и дни рождения
# ══════════════════════════════════════════════════════════

async def increment_visit_count(user_id: int) -> int:
    """Увеличить счётчик посещений. Возвращает новое значение."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET visit_count = COALESCE(visit_count, 0) + 1 WHERE user_id = ?",
            (user_id,)
        )
        await db.commit()
        async with db.execute("SELECT visit_count FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else 1


async def get_user_visit_count(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT visit_count FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def update_user_birthdate(user_id: int, birthdate: str) -> None:
    """Сохранить дату рождения в формате MM-DD."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET birthdate = ? WHERE user_id = ?", (birthdate, user_id)
        )
        await db.commit()


async def get_birthday_users_today() -> list[dict]:
    """Пользователи, у которых сегодня день рождения (поле birthdate = 'MM-DD')."""
    from datetime import date
    today_mmdd = date.today().strftime("%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE birthdate = ?", (today_mmdd,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ══════════════════════════════════════════════════════════
#  Отзывы
# ══════════════════════════════════════════════════════════

async def create_review(booking_id: int, user_id: int, master_id: str,
                        rating: int, comment: str = "") -> int:
    """Сохранить отзыв. Возвращает id."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT OR REPLACE INTO reviews (booking_id, user_id, master_id, rating, comment)
               VALUES (?, ?, ?, ?, ?)""",
            (booking_id, user_id, master_id, rating, comment)
        )
        await db.commit()
        return cur.lastrowid


async def get_review_by_booking(booking_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM reviews WHERE booking_id = ?", (booking_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_master_reviews(master_id: str, limit: int = 20) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM reviews WHERE master_id = ? ORDER BY created_at DESC LIMIT ?",
            (master_id, limit)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_avg_rating(master_id: str) -> float | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT AVG(rating) FROM reviews WHERE master_id = ?", (master_id,)
        ) as cur:
            row = await cur.fetchone()
            return round(row[0], 1) if row and row[0] is not None else None


async def get_bookings_for_review() -> list[dict]:
    """Вчерашние подтверждённые записи, по которым ещё не запрашивали отзыв."""
    from datetime import date, timedelta
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM bookings
               WHERE date = ? AND status = 'confirmed'
               AND (review_requested IS NULL OR review_requested = 0)""",
            (yesterday,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def mark_review_requested(booking_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE bookings SET review_requested = 1 WHERE id = ?", (booking_id,)
        )
        await db.commit()


# ══════════════════════════════════════════════════════════
#  Галерея работ
# ══════════════════════════════════════════════════════════

async def add_gallery_photo(master_id: str, category: str, file_id: str, caption: str = "") -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO gallery (master_id, category, file_id, caption) VALUES (?,?,?,?)",
            (master_id, category, file_id, caption)
        )
        await db.commit()
        return cur.lastrowid


async def get_gallery_by_category(category: str, limit: int = 20) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM gallery WHERE category = ? ORDER BY created_at DESC LIMIT ?",
            (category, limit)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_all_gallery(limit: int = 50) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM gallery ORDER BY created_at DESC LIMIT ?", (limit,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def delete_gallery_photo(photo_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM gallery WHERE id = ?", (photo_id,))
        await db.commit()


# ══════════════════════════════════════════════════════════
#  Заметки мастера о клиентах
# ══════════════════════════════════════════════════════════

async def save_client_note(master_id: str, client_user_id: int, note: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO client_notes (master_id, client_user_id, note, updated_at)
               VALUES (?, ?, ?, datetime('now'))
               ON CONFLICT(master_id, client_user_id) DO UPDATE SET
               note = excluded.note, updated_at = excluded.updated_at""",
            (master_id, client_user_id, note)
        )
        await db.commit()


async def get_client_note(master_id: str, client_user_id: int) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT note FROM client_notes WHERE master_id = ? AND client_user_id = ?",
            (master_id, client_user_id)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


# ══════════════════════════════════════════════════════════
#  Посещаемость
# ══════════════════════════════════════════════════════════

async def update_booking_attended(booking_id: int, attended: int) -> None:
    """attended: 1 = пришёл, 0 = не пришёл."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE bookings SET attended = ? WHERE id = ?", (attended, booking_id)
        )
        await db.commit()


# ══════════════════════════════════════════════════════════
#  Рассылка
# ══════════════════════════════════════════════════════════

async def get_all_user_ids() -> list[int]:
    """Все user_id для рассылки."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users") as cur:
            return [row[0] for row in await cur.fetchall()]


# ══════════════════════════════════════════════════════════
#  Отчёты
# ══════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════
#  Настройки салона
# ══════════════════════════════════════════════════════════

_settings_cache: dict = {}


async def seed_salon_settings() -> None:
    """Заполняет настройки значениями по умолчанию из salon.py (только если ключа нет)."""
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
        "specialist_label":   "мастер",
        "specialists_label":  "Специалисты",
        "photo_main":     "",
        "photo_services": "",
        "photo_masters":  "",
        "photo_booking":  "",
        "photo_about":    "",
        "photo_admin":    "",
    }
    async with aiosqlite.connect(DB_PATH) as db:
        for key, value in defaults.items():
            await db.execute(
                "INSERT OR IGNORE INTO salon_settings (key, value) VALUES (?, ?)",
                (key, value)
            )
        await db.commit()
    await _refresh_settings()


async def _refresh_settings() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT key, value FROM salon_settings") as cur:
            rows = await cur.fetchall()
    _settings_cache.clear()
    for row in rows:
        _settings_cache[row[0]] = row[1]


async def get_setting(key: str, default: str = "") -> str:
    if not _settings_cache:
        await _refresh_settings()
    return _settings_cache.get(key, default)


async def set_setting(key: str, value: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO salon_settings (key, value) VALUES (?, ?)",
            (key, value)
        )
        await db.commit()
    _settings_cache[key] = value


async def get_all_settings() -> dict:
    if not _settings_cache:
        await _refresh_settings()
    return dict(_settings_cache)


async def get_system_lang() -> str:
    """Системный язык салона — устанавливается админом, используется для данных в БД и уведомлений."""
    return await get_setting("default_lang", "ru")


# ══════════════════════════════════════════════════════════
#  GDPR
# ══════════════════════════════════════════════════════════

async def mark_gdpr_accepted(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET gdpr_accepted = 1 WHERE user_id = ?", (user_id,)
        )
        await db.commit()


async def delete_user_data(user_id: int) -> None:
    """Анонимизировать данные пользователя (право на забвение GDPR)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE users SET
               username = '[deleted]', full_name = '[deleted]',
               phone = NULL, birthdate = NULL, gdpr_accepted = 0
               WHERE user_id = ?""",
            (user_id,)
        )
        await db.execute(
            """UPDATE bookings SET
               user_name = '[deleted]', username = '[deleted]', phone = '[deleted]'
               WHERE user_id = ?""",
            (user_id,)
        )
        await db.commit()


# ══════════════════════════════════════════════════════════
#  Кастомные слоты мастера на день
# ══════════════════════════════════════════════════════════

async def add_master_custom_slot(master_id: str, date: str, time_start: str) -> bool:
    """Добавить кастомный слот. Возвращает True если добавлен, False если уже есть."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR IGNORE INTO master_custom_slots (master_id, date, time_start) VALUES (?,?,?)",
                (master_id, date, time_start)
            )
            await db.commit()
        return True
    except Exception:
        return False


async def get_master_custom_slots(master_id: str, date: str) -> list[dict]:
    """Все кастомные слоты мастера на дату, отсортированные по времени."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM master_custom_slots WHERE master_id=? AND date=? ORDER BY time_start",
            (master_id, date)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def has_master_custom_slots(master_id: str, date: str) -> bool:
    """Есть ли у мастера кастомные слоты на эту дату."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM master_custom_slots WHERE master_id=? AND date=?",
            (master_id, date)
        ) as cur:
            count = (await cur.fetchone())[0]
    return count > 0


async def delete_master_custom_slot(slot_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM master_custom_slots WHERE id=?", (slot_id,))
        await db.commit()


async def clear_master_custom_slots(master_id: str, date: str) -> None:
    """Удалить все кастомные слоты мастера на дату (только незанятые)."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Удаляем только слоты без бронирований
        await db.execute(
            """DELETE FROM master_custom_slots
               WHERE master_id=? AND date=?
               AND time_start NOT IN (
                   SELECT time_start FROM bookings
                   WHERE master_id=? AND date=? AND status NOT IN ('cancelled','rejected')
               )""",
            (master_id, date, master_id, date)
        )
        await db.commit()


async def get_period_stats(days: int) -> dict:
    """Статистика за последние N дней."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Записи за период
        async with db.execute(
            "SELECT COUNT(*) FROM bookings WHERE date >= date('now', ?)",
            (f"-{days} days",)
        ) as cur:
            bookings_total = (await cur.fetchone())[0]

        async with db.execute(
            "SELECT COUNT(*) FROM bookings WHERE date >= date('now', ?) AND status = 'confirmed'",
            (f"-{days} days",)
        ) as cur:
            bookings_confirmed = (await cur.fetchone())[0]

        # Новые клиенты
        async with db.execute(
            "SELECT COUNT(*) FROM users WHERE created_at >= datetime('now', ?)",
            (f"-{days} days",)
        ) as cur:
            new_clients = (await cur.fetchone())[0]

        # Топ услуги
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT service, COUNT(*) as cnt FROM bookings
               WHERE date >= date('now', ?) GROUP BY service ORDER BY cnt DESC LIMIT 5""",
            (f"-{days} days",)
        ) as cur:
            top_services = [dict(r) for r in await cur.fetchall()]

        # Топ мастера
        async with db.execute(
            """SELECT master, COUNT(*) as cnt FROM bookings
               WHERE date >= date('now', ?) GROUP BY master ORDER BY cnt DESC LIMIT 5""",
            (f"-{days} days",)
        ) as cur:
            top_masters = [dict(r) for r in await cur.fetchall()]

        # Средний рейтинг
        db.row_factory = None
        async with db.execute("SELECT AVG(rating) FROM reviews") as cur:
            avg_row = await cur.fetchone()
            avg_rating = round(avg_row[0], 1) if avg_row and avg_row[0] else None

        return {
            "days": days,
            "bookings_total": bookings_total,
            "bookings_confirmed": bookings_confirmed,
            "new_clients": new_clients,
            "top_services": top_services,
            "top_masters": top_masters,
            "avg_rating": avg_rating,
        }


# ══════════════════════════════════════════════════════════
#  Категории и услуги
# ══════════════════════════════════════════════════════════

async def seed_services() -> None:
    """Заполняет service_categories и services из salon.py если пустые."""
    from data.salon import SERVICES
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM service_categories") as cur:
            if (await cur.fetchone())[0] > 0:
                return
        for sort_i, (cat_key, cat) in enumerate(SERVICES.items()):
            await db.execute(
                "INSERT OR IGNORE INTO service_categories (cat_key, title, sort_order) VALUES (?,?,?)",
                (cat_key, cat["title"], sort_i)
            )
            for svc_sort, item in enumerate(cat["items"]):
                await db.execute(
                    """INSERT OR IGNORE INTO services
                       (service_id, category, name, price, duration, sort_order)
                       VALUES (?,?,?,?,?,?)""",
                    (item["id"], cat_key, item["name"], item["price"], item["duration"], svc_sort)
                )
        await db.commit()
    logger.info("Услуги перенесены в БД")


async def get_categories() -> list[dict]:
    """Все активные категории услуг, отсортированные."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM service_categories WHERE is_active=1 ORDER BY sort_order, cat_key"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_category_by_key(cat_key: str) -> dict | None:
    """Получить категорию по ключу."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM service_categories WHERE cat_key=?", (cat_key,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_db_services_by_category(category: str) -> list[dict]:
    """Активные услуги категории."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM services WHERE category=? AND is_active=1 ORDER BY sort_order, id",
            (category,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_db_service_by_id(service_id: str) -> dict | None:
    """Получить услугу по service_id."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM services WHERE service_id=?", (service_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_all_services_admin() -> list[dict]:
    """Все услуги включая неактивные — для панели администратора."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT s.*, sc.title as cat_title FROM services s
               LEFT JOIN service_categories sc ON s.category = sc.cat_key
               ORDER BY s.category, s.sort_order, s.id"""
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def add_db_service(service_id: str, category: str, name: str,
                         price: int, duration: int) -> None:
    """Добавить новую услугу."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO services (service_id, category, name, price, duration) VALUES (?,?,?,?,?)",
            (service_id, category, name, price, duration)
        )
        await db.commit()


async def update_db_service(service_id: str, **kwargs) -> None:
    """Обновить поля услуги."""
    allowed = {"name", "price", "duration", "sort_order", "is_active", "category"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [service_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE services SET {set_clause} WHERE service_id=?", values
        )
        await db.commit()


async def delete_db_service(service_id: str) -> None:
    """Удалить услугу."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM services WHERE service_id=?", (service_id,))
        await db.commit()


async def add_db_category(cat_key: str, title: str) -> None:
    """Добавить категорию услуг."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO service_categories (cat_key, title) VALUES (?,?)",
            (cat_key, title)
        )
        await db.commit()


async def update_db_category(cat_key: str, **kwargs) -> None:
    """Обновить категорию."""
    allowed = {"title", "sort_order", "is_active"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [cat_key]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE service_categories SET {set_clause} WHERE cat_key=?", values
        )
        await db.commit()


async def get_specialist_label() -> str:
    """Ярлык специалиста (ед.ч.) — мастер / тренер / врач / консультант."""
    return await get_setting("specialist_label", "мастер")


async def get_specialists_label() -> str:
    """Ярлык специалистов (мн.ч.) — для кнопки меню."""
    return await get_setting("specialists_label", "Специалисты")


# ══════════════════════════════════════════════════════════
#  Лог действий (audit log)
# ══════════════════════════════════════════════════════════

async def log_action(
    user_id: int,
    action: str,
    target: str = "",
    status: str = "ok",
    details: str = "",
) -> None:
    """Записывает действие в audit_log."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """INSERT INTO audit_log (user_id, action, target, status, details)
                   VALUES (?,?,?,?,?)""",
                (user_id, action, target, status, details),
            )
            await db.commit()
    except Exception as e:
        logger.error(f"log_action failed: {e}")


async def get_audit_log(limit: int = 50) -> list[dict]:
    """Возвращает последние `limit` записей лога."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]
