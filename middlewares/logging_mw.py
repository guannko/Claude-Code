"""
Middleware для логирования всех входящих сообщений.
Подключается один раз в main.py — работает для всех хендлеров.
"""

import logging
from typing import Any, Awaitable, Callable
from aiogram import BaseMiddleware
from aiogram.types import Message

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        user = event.from_user
        logger.info(
            "MSG | user_id=%s | username=@%s | text=%r",
            user.id if user else "?",
            user.username if user else "?",
            event.text or event.content_type,
        )
        return await handler(event, data)
