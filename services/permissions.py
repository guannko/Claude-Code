"""
Вспомогательные функции для проверки прав доступа.
"""

from config import ADMIN_ID
from database import is_admin_in_db


async def is_admin(user_id: int) -> bool:
    """True если пользователь — владелец (ADMIN_ID) или в таблице admins."""
    if user_id == ADMIN_ID:
        return True
    return await is_admin_in_db(user_id)


def is_owner(user_id: int) -> bool:
    """True только для владельца (ADMIN_ID)."""
    return user_id == ADMIN_ID
