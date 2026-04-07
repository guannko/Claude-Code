"""
Обработчики отзывов.

Клиент получает запрос отзыва на следующий день после визита (scheduler 10:00).
callback_data:
  review:rate:{booking_id}:{rating}  — оценка 1-5
  review:skip:{booking_id}           — пропустить
  review:comment:{booking_id}        — добавить комментарий после оценки
"""

import logging
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from database import (
    get_booking, create_review, get_review_by_booking,
    get_master, get_last_msg_id,
)
from states import ReviewStates

logger = logging.getLogger(__name__)
router = Router()

_STARS = {1: "⭐", 2: "⭐⭐", 3: "⭐⭐⭐", 4: "⭐⭐⭐⭐", 5: "⭐⭐⭐⭐⭐"}


def _rating_kb(booking_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⭐",     callback_data=f"review:rate:{booking_id}:1"),
            InlineKeyboardButton(text="⭐⭐",   callback_data=f"review:rate:{booking_id}:2"),
            InlineKeyboardButton(text="⭐⭐⭐", callback_data=f"review:rate:{booking_id}:3"),
        ],
        [
            InlineKeyboardButton(text="⭐⭐⭐⭐",   callback_data=f"review:rate:{booking_id}:4"),
            InlineKeyboardButton(text="⭐⭐⭐⭐⭐", callback_data=f"review:rate:{booking_id}:5"),
        ],
        [
            InlineKeyboardButton(text="Пропустить", callback_data=f"review:skip:{booking_id}"),
        ],
    ])


@router.callback_query(F.data.startswith("review:rate:"))
async def cb_review_rate(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    booking_id = int(parts[2])
    rating = int(parts[3])

    booking = await get_booking(booking_id)
    if not booking:
        await callback.answer("Запись не найдена.", show_alert=True)
        return

    existing = await get_review_by_booking(booking_id)
    if existing:
        await callback.answer("Вы уже оставили отзыв.", show_alert=True)
        return

    # Сохраняем оценку предварительно (без комментария)
    await create_review(booking_id, callback.from_user.id, booking.get("master_id", ""), rating)

    await state.set_state(ReviewStates.waiting_comment)
    await state.update_data(booking_id=booking_id, rating=rating)

    stars = _STARS.get(rating, str(rating))
    text = (
        f"Спасибо за оценку {stars}!\n\n"
        "Хотите оставить комментарий? Напишите его или нажмите «Пропустить»."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Пропустить", callback_data=f"review:skip_comment:{booking_id}"),
    ]])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("review:skip_comment:"))
async def cb_review_skip_comment(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "✅ Отзыв сохранён. Спасибо, что помогаете нам становиться лучше!"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("review:skip:"))
async def cb_review_skip(callback: CallbackQuery) -> None:
    await callback.message.edit_text("Хорошо, пропускаем. Будем рады видеть вас снова! 🌸")
    await callback.answer()


@router.message(StateFilter(ReviewStates.waiting_comment))
async def msg_review_comment(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    booking_id = data.get("booking_id")
    rating = data.get("rating", 5)

    if booking_id:
        await create_review(
            booking_id, message.from_user.id,
            (await get_booking(booking_id) or {}).get("master_id", ""),
            rating, message.text or ""
        )

    await state.clear()
    try:
        await message.delete()
    except Exception:
        pass
    await message.answer("✅ Спасибо за отзыв! Ваше мнение очень важно для нас 🌸")
