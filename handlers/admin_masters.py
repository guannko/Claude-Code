"""
Управление фотографиями мастеров — для администраторов.

callback_data схема:
  admin:master_photos           — список мастеров с фото-статусом
  admin:master_photo:{master_id} — запросить фото для мастера
"""

import logging

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery, Message,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext

from database import get_all_masters_with_photos, set_master_photo
from services.permissions import is_admin
from states import AdminStates

logger = logging.getLogger(__name__)
router = Router()

# Иконки категорий
_CAT_ICONS = {
    "manicure": "💅",
    "hair": "✂️",
    "barber": "🪒",
}
_CAT_NAMES = {
    "manicure": "Маникюр",
    "hair": "Стрижки",
    "barber": "Барбер",
}


def _master_photos_kb(masters: list[dict]) -> InlineKeyboardMarkup:
    """Клавиатура: каждый мастер — кнопка [Загрузить/Обновить фото]."""
    rows = []
    for m in masters:
        has_photo = bool(m.get("photo_file_id"))
        btn_text = f"{'Обновить' if has_photo else 'Загрузить'} фото — {m['name']}"
        rows.append([
            InlineKeyboardButton(
                text=btn_text,
                callback_data=f"admin:master_photo:{m['master_id']}",
            )
        ])
    rows.append([
        InlineKeyboardButton(text="◀️ Назад", callback_data="admin:refresh"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _build_photos_text(masters: list[dict]) -> str:
    """Текст экрана со статусом фото мастеров."""
    lines = ["📸 <b>Фото мастеров</b>\n"]

    # Группируем по категориям
    categories: dict[str, list[dict]] = {}
    for m in masters:
        cat = m.get("category", "other")
        categories.setdefault(cat, []).append(m)

    for cat, cat_masters in categories.items():
        icon = _CAT_ICONS.get(cat, "👩‍🎨")
        name = _CAT_NAMES.get(cat, cat.capitalize())
        lines.append(f"{icon} <b>{name}:</b>")
        for m in cat_masters:
            status = "✅" if m.get("photo_file_id") else "❌"
            lines.append(f"  {status} {m['name']}")
        lines.append("")

    return "\n".join(lines).rstrip()


# ── admin:master_photos — список мастеров с фото ───────────

@router.callback_query(F.data == "admin:master_photos")
async def cb_master_photos(callback: CallbackQuery) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    masters = await get_all_masters_with_photos()
    text = await _build_photos_text(masters)
    kb = _master_photos_kb(masters)

    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


# ── admin:master_photo:{master_id} — запросить фото ────────

@router.callback_query(F.data.startswith("admin:master_photo:"))
async def cb_master_photo_select(callback: CallbackQuery, state: FSMContext) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    master_id = callback.data[len("admin:master_photo:"):]

    # Найдём имя мастера из списка
    masters = await get_all_masters_with_photos()
    master = next((m for m in masters if m["master_id"] == master_id), None)
    master_name = master["name"] if master else master_id

    await state.set_state(AdminStates.uploading_master_photo)
    await state.update_data(
        photo_master_id=master_id,
        photo_master_name=master_name,
        photo_msg_id=callback.message.message_id,
    )

    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Отмена", callback_data="admin:master_photos"),
    ]])

    try:
        await callback.message.edit_text(
            f"📸 <b>Отправьте фото для мастера {master_name}</b>\n\n"
            "Просто пришлите фото (не документ).\n"
            "Фото будет показываться при выборе мастера.",
            reply_markup=cancel_kb,
        )
    except Exception:
        pass
    await callback.answer()


# ── Получили фото — сохраняем ───────────────────────────────

@router.message(AdminStates.uploading_master_photo)
async def msg_master_photo(message: Message, state: FSMContext) -> None:
    if not await is_admin(message.from_user.id):
        return

    data = await state.get_data()
    master_id = data.get("photo_master_id", "")
    master_name = data.get("photo_master_name", master_id)

    # Удаляем сообщение пользователя
    try:
        await message.delete()
    except Exception:
        pass

    if not message.photo:
        # Не фото — просим ещё раз
        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀️ Отмена", callback_data="admin:master_photos"),
        ]])
        await message.answer(
            "❌ Пожалуйста, пришлите именно фото (не документ и не стикер).\n\n"
            f"Фото для мастера <b>{master_name}</b>:",
            reply_markup=cancel_kb,
            parse_mode="HTML",
        )
        return

    file_id = message.photo[-1].file_id
    await set_master_photo(master_id, file_id)
    await state.clear()

    # Показываем обновлённый список
    masters = await get_all_masters_with_photos()
    text = "✅ <b>Фото сохранено!</b>\n\n" + await _build_photos_text(masters)
    kb = _master_photos_kb(masters)

    await message.answer(text, reply_markup=kb, parse_mode="HTML")


# ── Отмена FSM при нажатии "Назад" ─────────────────────────

@router.callback_query(AdminStates.uploading_master_photo, F.data == "admin:master_photos")
async def cb_cancel_photo_upload(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()

    masters = await get_all_masters_with_photos()
    text = await _build_photos_text(masters)
    kb = _master_photos_kb(masters)

    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        pass
    await callback.answer()
