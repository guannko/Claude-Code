"""
Конфигурация бота.
Все настройки берутся из .env файла.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Telegram ────────────────────────────────────────────
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
ADMIN_ID: int = int(os.getenv("ADMIN_ID", "0"))

# ── Настройки приложения ────────────────────────────
DEFAULT_LANG: str = os.getenv("DEFAULT_LANG", "ru")
DB_PATH: str = "database/bot.db"
LOG_PATH: str = "logs/bot.log"

# ── Groq AI ───────────────────────────────────────────
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

# ── Приветственное фото ─────────────────────────────────
WELCOME_PHOTO_URL: str = os.getenv("WELCOME_PHOTO_URL", "")

# ── Supabase (heartbeat → админка) ──────────────────────
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
BOT_ID: str = os.getenv("BOT_ID", "brain_index_bot")

# ── Валидация при старте ────────────────────────────
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан в .env файле")
