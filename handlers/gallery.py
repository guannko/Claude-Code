"""
Галерея работ салона.

Клиент:
  gallery:browse          — выбор категории
  gallery:cat:{category}  — листать фото категории (медиагруппы)

Мастер:
  gallery:master_upload   — загрузить своё фото в галерею

Администратор:
  gallery:admin           — список всех фото с возможностью удаления
  gallery:admin_upload    — загрузить фото (выбор категории + фото)
  gallery:del:{photo_id}  — удалить фото
"""

import logging
from aiogram import Router, F, Bot
from aiogram.types import (
    CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto,
)
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from database import (
    add_gallery_photo, get_gallery_by_category, get_all_gallery,
    delete_gallery_photo, get_master_by_telegram_id,
)
from services.permissions import is_admin
from services.sender import edit_menu
from data.salon import SECTION_PHOTOS
from states import GalleryStates

logger = logging.getLogger(__name__)
router = Router()

_GALLERY_PHOTO = SECTION_PHOTOS.get("services")

_CATEGORIES = {
    "manicure": "💅 Маникюр",
    "hair":     "✂️ Стрижка и окрашивание",
    "barber":   "🪒 Барбершоп",
}


def _category_browse_kb() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=v, callback_data=f"gallery:cat:{k}")]
            for k, v in _CATEGORIES.items()]
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _category_select_kb(back_cb: str = "gallery:admin") -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=v, callback_data=f"gallery:upload_cat:{k}")]
            for k, v in _CATEGORIES.items()]
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data=back_cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── Клиент: просмотр галереи ────────────────────────────────

@router.callback_query(F.data == "gallery:browse")
async def cb_gallery_browse(callback: CallbackQuery, bot: Bot) -> None:
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        "🖼 <b>Галерея работ</b>\n\nВыберите категорию:",
        _category_browse_kb(),
        photo_url=_GALLERY_PHOTO,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("gallery:cat:"))
async def cb_gallery_category(callback: CallbackQuery, bot: Bot) -> None:
    category = callback.data.split(":")[2]
    photos = await get_gallery_by_category(category, limit=10)
    cat_title = _CATEGORIES.get(category, category)

    back_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Назад к категориям", callback_data="gallery:browse"),
    ]])

    if not photos:
        await edit_menu(
            bot, callback.message.chat.id, callback.message.message_id,
            f"🖼 <b>{cat_title}</b>\n\nФотографий пока нет. Загляните позже!",
            back_kb, photo_url=_GALLERY_PHOTO,
        )
        await callback.answer()
        return

    # Показываем первое фото, остальные отправляем как отдельные
    first = photos[0]
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Назад", callback_data="gallery:browse"),
    ]])
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        f"🖼 <b>{cat_title}</b> — {len(photos)} фото",
        kb, photo_url=first["file_id"],
    )

    # Дополнительные фото отправляем отдельными сообщениями
    for p in photos[1:]:
        caption = p.get("caption") or ""
        try:
            await bot.send_photo(
                chat_id=callback.message.chat.id,
                photo=p["file_id"],
                caption=caption,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning("gallery send_photo: %s", e)

    await callback.answer()


# ── Мастер: загрузка своей работы ──────────────────────────

@router.callback_query(F.data == "gallery:master_upload")
async def cb_gallery_master_upload(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    master = await get_master_by_telegram_id(callback.from_user.id)
    if not master:
        await callback.answer("⛔ Только мастера могут загружать фото.", show_alert=True)
        return

    await state.set_state(GalleryStates.choosing_category)
    await state.update_data(source="master", master_id=master["master_id"],
                            back_cb="mst_panel:home")
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        "🖼 Выберите категорию для фото:",
        _category_select_kb(back_cb="mst_panel:home"),
        photo_url=_GALLERY_PHOTO,
    )
    await callback.answer()


# ── Администратор: управление галереей ──────────────────────

@router.callback_query(F.data == "gallery:admin")
async def cb_gallery_admin(callback: CallbackQuery, bot: Bot) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    photos = await get_all_gallery(limit=50)
    lines = [f"🖼 <b>Галерея работ</b> — {len(photos)} фото\n"]
    if photos:
        for p in photos[:10]:
            cat = _CATEGORIES.get(p["category"], p["category"])
            lines.append(f"• {cat}: {p.get('caption') or '—'} [id:{p['id']}]")
        if len(photos) > 10:
            lines.append(f"... и ещё {len(photos) - 10}")
    else:
        lines.append("Галерея пуста.")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить фото", callback_data="gallery:admin_upload")],
        [InlineKeyboardButton(text="🗑 Удалить фото",  callback_data="gallery:admin_delete_list")],
        [InlineKeyboardButton(text="◀️ Назад",         callback_data="adm:panel")],
    ])
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        "\n".join(lines), kb, photo_url=_GALLERY_PHOTO,
    )
    await callback.answer()


@router.callback_query(F.data == "gallery:admin_upload")
async def cb_gallery_admin_upload(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    await state.set_state(GalleryStates.choosing_category)
    await state.update_data(source="admin", master_id="", back_cb="gallery:admin")
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        "🖼 Выберите категорию для нового фото:",
        _category_select_kb(back_cb="gallery:admin"),
        photo_url=_GALLERY_PHOTO,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("gallery:upload_cat:"))
async def cb_gallery_upload_cat(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    category = callback.data.split(":")[2]
    await state.update_data(category=category)
    await state.set_state(GalleryStates.uploading_photo)

    data = await state.get_data()
    back_cb = data.get("back_cb", "gallery:admin")
    cat_title = _CATEGORIES.get(category, category)

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Отмена", callback_data=back_cb),
    ]])
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        f"📸 Категория: <b>{cat_title}</b>\n\nОтправьте фото для загрузки в галерею:",
        kb, photo_url=_GALLERY_PHOTO,
    )
    await callback.answer()


@router.message(StateFilter(GalleryStates.uploading_photo), F.photo)
async def msg_gallery_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    file_id = message.photo[-1].file_id
    await state.update_data(file_id=file_id)
    await state.set_state(GalleryStates.entering_caption)

    try:
        await message.delete()
    except Exception:
        pass

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Без подписи", callback_data="gallery:no_caption"),
    ]])
    await message.answer("✅ Фото получено!\n\nДобавьте подпись или нажмите «Без подписи»:",
                         reply_markup=kb)


@router.callback_query(F.data == "gallery:no_caption", StateFilter(GalleryStates.entering_caption))
async def cb_gallery_no_caption(callback: CallbackQuery, state: FSMContext) -> None:
    await _save_gallery_photo(callback.message, state, caption="")
    await callback.answer()


@router.message(StateFilter(GalleryStates.entering_caption))
async def msg_gallery_caption(message: Message, state: FSMContext) -> None:
    caption = message.text or ""
    try:
        await message.delete()
    except Exception:
        pass
    await _save_gallery_photo(message, state, caption=caption)


async def _save_gallery_photo(message: Message, state: FSMContext, caption: str) -> None:
    data = await state.get_data()
    file_id = data.get("file_id", "")
    category = data.get("category", "")
    master_id = data.get("master_id", "")
    await state.clear()

    if file_id and category:
        await add_gallery_photo(master_id, category, file_id, caption)
        cat_title = _CATEGORIES.get(category, category)
        await message.answer(f"✅ Фото добавлено в галерею «{cat_title}»!")
    else:
        await message.answer("⚠️ Не удалось сохранить фото.")


# ── Администратор: удаление фото ───────────────────────────

@router.callback_query(F.data == "gallery:admin_delete_list")
async def cb_gallery_delete_list(callback: CallbackQuery, bot: Bot) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    photos = await get_all_gallery(limit=30)
    if not photos:
        await callback.answer("Галерея пуста.", show_alert=True)
        return

    rows = []
    for p in photos[:20]:
        cat = _CATEGORIES.get(p["category"], p["category"])
        label = f"🗑 {cat}: {(p.get('caption') or '—')[:20]} [#{p['id']}]"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"gallery:del:{p['id']}")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="gallery:admin")])

    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        "🗑 <b>Удалить фото</b>\n\nНажмите на фото для удаления:",
        InlineKeyboardMarkup(inline_keyboard=rows),
        photo_url=_GALLERY_PHOTO,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("gallery:del:"))
async def cb_gallery_delete(callback: CallbackQuery, bot: Bot) -> None:
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    photo_id = int(callback.data.split(":")[2])
    await delete_gallery_photo(photo_id)
    await callback.answer("✅ Фото удалено.")
    # Обновляем список
    await cb_gallery_delete_list(callback, bot)
