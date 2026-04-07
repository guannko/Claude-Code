"""
Антиспам middleware — работает и для Message, и для CallbackQuery.
Защищает от дублей /start и двойных нажатий кнопок.
"""

import time
import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject

logger = logging.getLogger(__name__)


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, throttle_time: float = 0.8) -> None:
        self.throttle_time = throttle_time
        self._last_action: dict[int, float] = {}  # user_id -> timestamp

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Получаем user_id из любого типа события
        user = getattr(event, "from_user", None)
        if user is None:
            return await handler(event, data)

        user_id = user.id
        now = time.monotonic()

        if now - self._last_action.get(user_id, 0.0) < self.throttle_time:
            logger.debug("Throttled event from user_id=%s", user_id)
            # Для callback убираем "часики"
            if isinstance(event, CallbackQuery):
                await event.answer()
            # Для Message — тихо удаляем дубль
            elif isinstance(event, Message):
                try:
                    await event.delete()
                except Exception:
                    pass
            return

        self._last_action[user_id] = now
        return await handler(event, data)
