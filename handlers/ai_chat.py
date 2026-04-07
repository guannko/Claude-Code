"""
AI-ассистент салона. Отвечает на вопросы о салоне через Groq API.

Модель: llama-3.3-70b-versatile
HTTP-клиент: aiohttp (уже есть как зависимость aiogram)
"""

import logging
import aiohttp

from aiogram import Router, Bot, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from config import GROQ_API_KEY
from database import get_user_lang, get_setting, get_categories, get_db_services_by_category, get_masters_by_category
from services.sender import edit_menu
from states import AiChatStates
from texts import t
from data.salon import SECTION_PHOTOS

logger = logging.getLogger(__name__)
router = Router()

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"


async def _get_system_prompt() -> str:
    """Строит системный промпт с актуальными данными из БД."""
    salon_name     = await get_setting("salon_name",           "Studio ONE")
    salon_address  = await get_setting("salon_address",        "")
    salon_metro    = await get_setting("salon_metro",          "")
    salon_phone    = await get_setting("salon_phone",          "")
    salon_instagram= await get_setting("salon_instagram",      "")
    salon_since    = await get_setting("salon_since",          "")
    hours_wd       = await get_setting("salon_hours_weekdays", "")
    hours_we       = await get_setting("salon_hours_weekends", "")
    currency       = await get_setting("currency",             "₽")

    lines = [
        f"Ты — вежливый AI-ассистент салона красоты {salon_name}.",
        "Отвечай только на вопросы о салоне. Будь кратким и полезным.",
        "",
        "ИНФОРМАЦИЯ О САЛОНЕ:",
        f"Название: {salon_name}",
    ]
    if salon_address:
        metro_str = f" ({salon_metro})" if salon_metro else ""
        lines.append(f"Адрес: {salon_address}{metro_str}")
    if salon_phone:
        lines.append(f"Телефон: {salon_phone}")
    if salon_instagram:
        lines.append(f"Instagram: {salon_instagram}")
    if salon_since:
        lines.append(f"Работаем с {salon_since} года.")
    if hours_wd or hours_we:
        lines += ["", "Режим работы:"]
        if hours_wd:
            lines.append(f"  {hours_wd}")
        if hours_we:
            lines.append(f"  {hours_we}")

    # Услуги из БД
    categories = await get_categories()
    if categories:
        lines += ["", "УСЛУГИ И ЦЕНЫ:"]
        for cat in categories:
            lines.append(f"\n{cat['title']}:")
            items = await get_db_services_by_category(cat["cat_key"])
            for item in items:
                dur = item["duration"]
                if dur < 60:
                    dur_str = f"{dur} мин"
                else:
                    h = dur / 60
                    dur_str = f"{int(h)} ч" if h == int(h) else f"{h} ч"
                lines.append(f"  - {item['name']} — {item['price']}{currency} / {dur_str}")

    # Мастера из БД
    all_masters = []
    for cat in categories:
        masters = await get_masters_by_category(cat["cat_key"])
        if masters:
            lines.append(f"\n{cat['title']} — мастера:")
            for m in masters:
                desc = m.get("description") or ""
                line = f"  - {m['name']}"
                if desc:
                    line += f", специализация: {desc}"
                lines.append(line)

    lines += [
        "",
        "Если вопрос не о салоне — вежливо скажи что отвечаешь только на вопросы о салоне.",
        "Отвечай в 2-4 предложения максимум.",
    ]
    return "\n".join(lines)


# ── Клавиатуры ────────────────────────────────────────────

def _ai_prompt_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="ai:back")]
    ])


def _ai_answer_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🤖 Ещё вопрос", callback_data="menu:ai_chat"),
            InlineKeyboardButton(text="◀️ Меню",        callback_data="menu:main"),
        ]
    ])


# ── Кнопка "Назад" из AI-чата ─────────────────────────────

@router.callback_query(F.data == "ai:back")
async def cb_ai_back(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    from keyboards import main_menu_kb, main_menu_with_admin_kb
    from database import get_setting
    from services.permissions import is_admin as _is_admin
    await state.clear()
    lang = await get_user_lang(callback.from_user.id)
    salon_name = await get_setting("salon_name", "Салон красоты")
    if await _is_admin(callback.from_user.id):
        kb = main_menu_with_admin_kb(lang)
    else:
        kb = main_menu_kb(lang)
    await edit_menu(
        bot, callback.message.chat.id, callback.message.message_id,
        t("main_menu_text", lang, name=callback.from_user.first_name, salon_name=salon_name),
        kb,
        photo_url=SECTION_PHOTOS.get("main"),
    )
    await callback.answer()


# ── Обработка текстового вопроса пользователя ─────────────

@router.message(AiChatStates.waiting_question)
async def msg_ai_question(message: Message, bot: Bot, state: FSMContext) -> None:
    question = message.text.strip() if message.text else ""
    lang = await get_user_lang(message.from_user.id)

    # Удаляем сообщение пользователя
    try:
        await message.delete()
    except Exception:
        pass

    data = await state.get_data()
    msg_id = data.get("ai_msg_id")

    if not question:
        return

    # Показываем "думаю..."
    try:
        await edit_menu(
            bot, message.chat.id, msg_id,
            t("ai_chat_thinking", lang),
            InlineKeyboardMarkup(inline_keyboard=[]),
            photo_url=SECTION_PHOTOS.get("ai"),
        )
    except Exception:
        pass

    # Запрос к Groq или заглушка
    if not GROQ_API_KEY:
        answer = t("ai_chat_unavailable", lang)
    else:
        answer = await _ask_groq(question)
        if answer is None:
            answer = t("ai_chat_error", lang)

    # Форматируем ответ
    response_text = (
        f"🤖 <b>Вопрос:</b> {question}\n\n"
        f"💬 <b>Ответ:</b>\n{answer}"
    )

    await edit_menu(
        bot, message.chat.id, msg_id,
        response_text, _ai_answer_kb(),
        photo_url=SECTION_PHOTOS.get("ai"),
    )

    # Остаёмся в состоянии waiting_question для следующего вопроса


# ── Groq API запрос ───────────────────────────────────────

async def _ask_groq(question: str) -> str | None:
    """Отправить вопрос в Groq, вернуть текст ответа или None при ошибке."""
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": await _get_system_prompt()},
            {"role": "user",   "content": question},
        ],
        "max_tokens": 512,
        "temperature": 0.5,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                GROQ_URL,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"].strip()
                else:
                    body = await resp.text()
                    logger.error("Groq API error %s: %s", resp.status, body[:200])
                    return None
    except Exception as e:
        logger.error("Groq request failed: %s", e)
        return None
