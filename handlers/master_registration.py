"""
Регистрация мастера в системе.

/master → бот спрашивает код мастера
→ пользователь вводит код (например "anna_k")
→ бот проверяет наличие в таблице masters
→ если найден — привязывает telegram_user_id
→ если нет — сообщает об ошибке
"""

import logging
from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from database import get_master, set_master_telegram_id, get_master_by_telegram_id
from states import MasterRegStates

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("master"))
async def cmd_master(message: Message, state: FSMContext) -> None:
    """Начало регистрации мастера."""
    # Проверяем — вдруг уже зарегистрирован
    existing = await get_master_by_telegram_id(message.from_user.id)
    if existing:
        await message.answer(
            f"✅ Вы уже зарегистрированы как <b>{existing['name']}</b>.\n"
            f"Код мастера: <code>{existing['master_id']}</code>",
            parse_mode="HTML",
        )
        return

    await state.set_state(MasterRegStates.waiting_code)
    await message.answer(
        "🔑 <b>Регистрация мастера</b>\n\n"
        "Введите ваш код мастера:\n"
        "<i>(например: anna_k, dmitry_r)</i>",
        parse_mode="HTML",
    )


@router.message(MasterRegStates.waiting_code)
async def msg_master_code(message: Message, state: FSMContext) -> None:
    """Обработка введённого кода мастера."""
    code = message.text.strip().lower()

    master = await get_master(code)

    if not master:
        await message.answer(
            "❌ <b>Код не найден.</b>\n\n"
            "Обратитесь к администратору для получения кода мастера.",
            parse_mode="HTML",
        )
        await state.clear()
        return

    # Проверяем — не привязан ли этот мастер к другому аккаунту
    if master.get("telegram_user_id") and master["telegram_user_id"] != message.from_user.id:
        await message.answer(
            "⚠️ Этот код уже используется другим аккаунтом.\n"
            "Обратитесь к администратору.",
            parse_mode="HTML",
        )
        await state.clear()
        return

    await set_master_telegram_id(code, message.from_user.id)
    await state.clear()

    await message.answer(
        f"✅ <b>Вы зарегистрированы как {master['name']}!</b>\n\n"
        f"Теперь вы будете получать уведомления о новых записях и сможете "
        f"принимать или отклонять их прямо в боте.",
        parse_mode="HTML",
    )
    logger.info(
        "Мастер зарегистрирован: %s (telegram_id=%s)",
        code, message.from_user.id,
    )
