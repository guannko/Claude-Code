"""Лицензирование Studio ONE — для self-hosted деплоя всегда активно."""
import logging

logger = logging.getLogger(__name__)

_ALWAYS_ACTIVE = {
    "active": True,
    "mode": "licensed",
    "days_left": 36500,
    "hours_left": 876000,
    "expires_at": None,
}


async def init_license_table() -> None:
    pass


async def init_trial() -> None:
    pass


async def get_license_status() -> dict:
    return _ALWAYS_ACTIVE


async def activate_license(key: str) -> dict:
    return {"ok": True, "expires": None}
