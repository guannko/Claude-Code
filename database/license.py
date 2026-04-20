"""Лицензирование Studio ONE — триал + месячная подписка."""
import aiosqlite
import re
import logging
from datetime import datetime, timezone, timedelta
from config import DB_PATH

logger = logging.getLogger(__name__)


async def init_license_table() -> None:
    """Создать таблицу license при старте."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS license (
                id               INTEGER PRIMARY KEY CHECK (id = 1),
                trial_started_at TEXT    DEFAULT NULL,
                license_key      TEXT    DEFAULT NULL,
                license_expires  TEXT    DEFAULT NULL,
                activated_at     TEXT    DEFAULT NULL
            )
        """)
        await db.execute("INSERT OR IGNORE INTO license (id) VALUES (1)")
        await db.commit()


async def init_trial() -> None:
    """Запустить 3-дневный триал если ещё не запущен."""
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            "SELECT trial_started_at FROM license WHERE id=1"
        )).fetchone()
        if row and row[0]:
            return
        now = datetime.now(timezone.utc).isoformat()
        await db.execute("UPDATE license SET trial_started_at=? WHERE id=1", (now,))
        await db.commit()
    logger.info("🆓 Trial period started")


async def get_license_status() -> dict:
    """
    Возвращает статус лицензии:
    {active, mode: 'new'|'trial'|'licensed'|'expired', days_left, hours_left, expires_at}
    """
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            "SELECT trial_started_at, license_key, license_expires FROM license WHERE id=1"
        )).fetchone()

    if not row:
        return {"active": True, "mode": "new", "days_left": 3, "hours_left": 72, "expires_at": None}

    trial_started, lic_key, lic_expires = row
    now = datetime.now(timezone.utc)

    # Активная коммерческая лицензия
    if lic_key and lic_expires:
        try:
            exp = datetime.fromisoformat(lic_expires)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp > now:
                remaining = exp - now
                return {
                    "active": True, "mode": "licensed",
                    "days_left": remaining.days,
                    "hours_left": int(remaining.total_seconds() / 3600),
                    "expires_at": lic_expires,
                }
        except Exception:
            pass

    # Триальный период
    if trial_started:
        try:
            started = datetime.fromisoformat(trial_started)
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            trial_end = started + timedelta(days=3)
            if trial_end > now:
                remaining = trial_end - now
                return {
                    "active": True, "mode": "trial",
                    "days_left": remaining.days,
                    "hours_left": int(remaining.total_seconds() / 3600),
                    "expires_at": trial_end.isoformat(),
                }
            return {"active": False, "mode": "expired", "days_left": 0, "hours_left": 0, "expires_at": None}
        except Exception:
            pass

    return {"active": True, "mode": "new", "days_left": 3, "hours_left": 72, "expires_at": None}


async def activate_license(key: str) -> dict:
    """
    Активировать лицензионный ключ формата STUDIO-XXXX-XXXX-XXXX.
    Даёт 30 дней полного доступа.
    Возвращает {"ok": True, "expires": "..."} или {"ok": False, "error": "..."}.
    """
    key = key.strip().upper()
    if not re.match(r'^STUDIO-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$', key):
        return {"ok": False, "error": "Неверный формат. Ожидается: STUDIO-XXXX-XXXX-XXXX"}

    now = datetime.now(timezone.utc)
    expires = (now + timedelta(days=30)).isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE license SET license_key=?, license_expires=?, activated_at=? WHERE id=1",
            (key, expires, now.isoformat()),
        )
        await db.commit()

    logger.info("✅ License activated: %s, expires: %s", key, expires)
    return {"ok": True, "expires": expires}
