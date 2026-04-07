"""Fallback для необработанных сообщений. Регистрируется ПОСЛЕДНИМ."""

import logging
from aiogram import Router, Bot, F
from aiogram.types import Message
from aiogram.filters import StateFilter
from aiogram.fsm.state import default_state
from database import get_user_lang
from services.sender import send_menu
from keyboards import main_menu_kb
from texts import t
from data.salon import SECTION_PHOTOS

logger = logging.getLogger(__name__)
router = Router()


@router.message(StateFilter(default_state))
async def unknown_message(message: Message, bot: Bot) -> None:
    """Любое текстовое сообщение вне FSM → возврат в меню."""
    from database import get_setting
    from services.permissions import is_admin as _is_admin
    from keyboards import main_menu_with_admin_kb
    lang = await get_user_lang(message.from_user.id)
    salon_name = await get_setting("salon_name", "Салон красоты")
    logger.warning("Необработанное: %r от %s", message.text, message.from_user.id)
    if await _is_admin(message.from_user.id):
        kb = main_menu_with_admin_kb(lang)
    else:
        kb = main_menu_kb(lang)
    await send_menu(
        message, bot,
        t("main_menu_text", lang, name=message.from_user.first_name, salon_name=salon_name),
        kb,
        photo_url=SECTION_PHOTOS.get("main"),
    )
