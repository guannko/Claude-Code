"""Middleware: проверка лицензии перед обработкой сообщений клиентов."""

import logging
from typing import Callable, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

logger = logging.getLogger(__name__)


class LicenseMiddleware(BaseMiddleware):
    """
    Пропускает администраторов всегда.
    Для обычных пользователей проверяет активность лицензии/триала.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id: int | None = None
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id

        if user_id is None:
            return await handler(event, data)

        # Администраторы проходят всегда
        from services.permissions import is_admin
        if await is_admin(user_id):
            return await handler(event, data)

        # Проверяем лицензию
        try:
            from database.license import get_license_status
            status = await get_license_status()
            if status.get("active", True):
                return await handler(event, data)
        except Exception:
            # При ошибке пропускаем — не блокируем работу
            return await handler(event, data)

        # Лицензия истекла
        if isinstance(event, Message):
            try:
                await event.answer(
                    "⏸ <b>Бот временно приостановлен.</b>\n\n"
                    "Пожалуйста, свяжитесь с администратором.",
                    parse_mode="HTML",
                )
            except Exception:
                pass
        elif isinstance(event, CallbackQuery):
            try:
                await event.answer("⏸ Бот временно приостановлен", show_alert=True)
            except Exception:
                pass

        return None
