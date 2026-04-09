"""
Heartbeat — бот раз в 30 сек пишет статус в Supabase.
Админка подписана на Realtime и показывает статус мгновенно.
"""

import asyncio
import logging
from datetime import datetime, timezone

from config import SUPABASE_URL, SUPABASE_KEY, BOT_ID

logger = logging.getLogger(__name__)

_sb = None


def _get_client():
    global _sb
    if _sb is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            return None
        from supabase import create_client
        _sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _sb


async def heartbeat_loop(interval: int = 30) -> None:
    """Runs as asyncio.Task in main(). Non-blocking."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.warning("Heartbeat отключён: SUPABASE_URL / SUPABASE_KEY не заданы")
        return

    logger.info(f"Heartbeat запущен (bot_id={BOT_ID}, интервал={interval}с)")
    while True:
        try:
            sb = _get_client()
            if sb:
                sb.table("heartbeats").upsert({
                    "bot_id": BOT_ID,
                    "status": "online",
                    "pinged_at": datetime.now(timezone.utc).isoformat(),
                }).execute()
        except Exception as e:
            logger.error(f"Heartbeat ошибка: {e}")
        await asyncio.sleep(interval)


async def set_offline() -> None:
    """Call on bot shutdown — sets status to offline."""
    try:
        sb = _get_client()
        if sb:
            sb.table("heartbeats").upsert({
                "bot_id": BOT_ID,
                "status": "offline",
                "pinged_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
            logger.info("Heartbeat: статус → offline")
    except Exception as e:
        logger.error(f"Heartbeat set_offline ошибка: {e}")
