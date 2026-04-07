"""
Данные салона красоты Studio ONE.
Все константы — меняй здесь при смене клиента.
"""

# ── Фото для каждого раздела ──────────────────────────────
_SECTION_PHOTOS_DEFAULT = {
    "main":      "https://images.unsplash.com/photo-1560066984-138dadb4c035?w=800",
    "services":  "https://images.unsplash.com/photo-1522337360788-8b13dee7a37e?w=800",
    "manicure":  "https://images.unsplash.com/photo-1604654894610-df63bc536371?w=800",
    "hair":      "https://images.unsplash.com/photo-1522337360788-8b13dee7a37e?w=800",
    "barber":    "https://images.unsplash.com/photo-1503951914875-452162b0f3f1?w=800",
    "masters":   "https://images.unsplash.com/photo-1521590832167-7bcbfaa6381f?w=800",
    "about":     "https://images.unsplash.com/photo-1560066984-138dadb4c035?w=800",
    "booking":   "https://images.unsplash.com/photo-1540555700478-4be289fbecef?w=800",
    "mybookings":"https://images.unsplash.com/photo-1611078489935-0cb964de46d6?w=800",
    "ai":        "https://images.unsplash.com/photo-1677442135703-1787eea5ce01?w=800",
    "admin":     "https://images.unsplash.com/photo-1552664730-d307ca884978?w=800",
}


class _SectionPhotosProxy:
    """Фото секций: сначала проверяет кэш настроек (photo_{key}), потом дефолт."""

    def get(self, key: str, default=None):
        try:
            from database.db import _settings_cache
            cached = _settings_cache.get(f"photo_{key}", "")
            if cached:
                return cached
        except Exception:
            pass
        return _SECTION_PHOTOS_DEFAULT.get(key, default)

    def __getitem__(self, key: str):
        result = self.get(key)
        if result is None:
            raise KeyError(key)
        return result

    def __contains__(self, key: str):
        return key in _SECTION_PHOTOS_DEFAULT


SECTION_PHOTOS = _SectionPhotosProxy()

# Временные фото мастеров (Unsplash) — заменяются реальными через /admin
MASTER_PHOTOS = {
    "anna_k":   "https://images.unsplash.com/photo-1604654894610-df63bc536371?w=400",
    "maria_s":  "https://images.unsplash.com/photo-1522337660859-02fbefca4702?w=400",
    "elena_v":  "https://images.unsplash.com/photo-1580618672591-eb180b1a973f?w=400",
    "olga_m":   "https://images.unsplash.com/photo-1562322140-8baeececf3df?w=400",
    "dmitry_r": "https://images.unsplash.com/photo-1503951914875-452162b0f3f1?w=400",
    "artem_k":  "https://images.unsplash.com/photo-1621605815971-8f41b1d4e601?w=400",
}

SALON_NAME = "Studio ONE"
SALON_ADDRESS = "ул. Арбат 24, Москва"
SALON_METRO = "м. Арбатская, 5 минут пешком"
SALON_SINCE = "2018"
SALON_PHONE = "+7 (495) 123-45-67"
SALON_INSTAGRAM = "@studio_one_msk"

SALON_HOURS = {
    "weekdays": "Пн–Пт: 10:00 – 21:00",
    "weekends": "Сб–Вс: 10:00 – 20:00",
}

# ── Услуги ────────────────────────────────────────────────────
# duration — в минутах, price — в рублях

SERVICES = {
    "manicure": {
        "title": "💅 Маникюр",
        "items": [
            {"id": "man_1", "name": "Классический маникюр",  "price": 800,  "duration": 45},
            {"id": "man_2", "name": "Маникюр + гель-лак",    "price": 1500, "duration": 90},
            {"id": "man_3", "name": "Наращивание ногтей",    "price": 2800, "duration": 150},
            {"id": "man_4", "name": "Педикюр классический",  "price": 1200, "duration": 60},
            {"id": "man_5", "name": "Педикюр + гель-лак",    "price": 1800, "duration": 90},
        ],
    },
    "hair": {
        "title": "✂️ Стрижка и окрашивание",
        "items": [
            {"id": "hair_1", "name": "Женская стрижка",        "price": 1500, "duration": 60},
            {"id": "hair_2", "name": "Мужская стрижка",        "price": 900,  "duration": 45},
            {"id": "hair_3", "name": "Окрашивание (корни)",    "price": 2500, "duration": 120},
            {"id": "hair_4", "name": "Окрашивание (полное)",   "price": 4000, "duration": 180},
            {"id": "hair_5", "name": "Ламинирование волос",    "price": 3500, "duration": 120},
            {"id": "hair_6", "name": "Укладка",                "price": 800,  "duration": 45},
        ],
    },
    "barber": {
        "title": "🪒 Барбершоп",
        "items": [
            {"id": "bar_1", "name": "Мужская стрижка",              "price": 900,  "duration": 45},
            {"id": "bar_2", "name": "Стрижка + борода",             "price": 1400, "duration": 90},
            {"id": "bar_3", "name": "Оформление бороды",            "price": 600,  "duration": 30},
            {"id": "bar_4", "name": "Королевское бритьё",           "price": 800,  "duration": 45},
            {"id": "bar_5", "name": "Детская стрижка (до 12 лет)",  "price": 600,  "duration": 30},
        ],
    },
}

# ── Мастера ───────────────────────────────────────────────────

MASTERS = {
    "manicure": [
        {"id": "m_anna",  "name": "Анна К.",   "exp": 7, "spec": "наращивание, дизайн"},
        {"id": "m_maria", "name": "Мария С.",  "exp": 4, "spec": "гель-лак, педикюр"},
    ],
    "hair": [
        {"id": "m_elena", "name": "Елена В.",  "exp": 10, "spec": "окрашивание, колористика"},
        {"id": "m_olga",  "name": "Ольга М.",  "exp": 6,  "spec": "женские стрижки, укладки"},
    ],
    "barber": [
        {"id": "m_dmitry", "name": "Дмитрий Р.", "exp": 8, "spec": "классические стрижки, борода"},
        {"id": "m_artem",  "name": "Артём К.",   "exp": 5, "spec": "фейд, тейп"},
    ],
}


# Расписание мастеров
# working_days: 0=Пн, 1=Вт, 2=Ср, 3=Чт, 4=Пт, 5=Сб, 6=Вс
MASTER_SCHEDULE = {
    "anna_k": {
        "name": "Анна К.",
        "category": "manicure",
        "working_days": [0, 1, 2, 3, 4],       # Пн-Пт
        "start": "10:00",
        "end": "20:00",
    },
    "maria_s": {
        "name": "Мария С.",
        "category": "manicure",
        "working_days": [1, 2, 3, 4, 5],       # Вт-Сб
        "start": "11:00",
        "end": "21:00",
    },
    "elena_v": {
        "name": "Елена В.",
        "category": "hair",
        "working_days": [0, 1, 2, 3, 4],
        "start": "10:00",
        "end": "20:00",
    },
    "olga_m": {
        "name": "Ольга М.",
        "category": "hair",
        "working_days": [2, 3, 4, 5, 6],       # Ср-Вс
        "start": "10:00",
        "end": "20:00",
    },
    "dmitry_r": {
        "name": "Дмитрий Р.",
        "category": "barber",
        "working_days": [0, 1, 2, 3, 4],
        "start": "10:00",
        "end": "21:00",
    },
    "artem_k": {
        "name": "Артём К.",
        "category": "barber",
        "working_days": [1, 2, 3, 4, 5, 6],   # Вт-Вс
        "start": "11:00",
        "end": "21:00",
    },
}

# Связь id услуги → master_id
# Используется для "Любого мастера"
CATEGORY_MASTERS = {
    "manicure": ["anna_k", "maria_s"],
    "hair": ["elena_v", "olga_m"],
    "barber": ["dmitry_r", "artem_k"],
}

SLOT_INTERVAL = 30  # минут между слотами
BOOKING_DAYS_AHEAD = 14  # на сколько дней вперёд показываем запись


def _fmt_duration(minutes: int) -> str:
    """Форматирует минуты: 45 → '45 мин', 90 → '1.5 ч', 60 → '1 ч'."""
    if minutes < 60:
        return f"{minutes} мин"
    hours = minutes / 60
    if hours == int(hours):
        return f"{int(hours)} ч"
    return f"{hours} ч"


def build_system_prompt() -> str:
    """Строит системный промпт для Groq с полными данными салона."""
    lines = [
        f"Ты — вежливый AI-ассистент салона красоты {SALON_NAME}.",
        "Отвечай только на вопросы о салоне. Будь кратким и полезным.",
        "",
        "ИНФОРМАЦИЯ О САЛОНЕ:",
        f"Название: {SALON_NAME}",
        f"Адрес: {SALON_ADDRESS} ({SALON_METRO})",
        f"Телефон: {SALON_PHONE}",
        f"Instagram: {SALON_INSTAGRAM}",
        f"Работаем с {SALON_SINCE} года.",
        "",
        "Режим работы:",
        f"  {SALON_HOURS['weekdays']}",
        f"  {SALON_HOURS['weekends']}",
        "",
        "УСЛУГИ И ЦЕНЫ:",
    ]

    for cat_key, cat in SERVICES.items():
        lines.append(f"\n{cat['title']}:")
        for item in cat["items"]:
            dur = _fmt_duration(item["duration"])
            lines.append(f"  - {item['name']} — {item['price']}₽ / {dur}")

    lines.append("\nМАСТЕРА:")
    for cat_key, masters in MASTERS.items():
        cat_title = SERVICES[cat_key]["title"]
        lines.append(f"\n{cat_title}:")
        for m in masters:
            lines.append(f"  - {m['name']}, стаж {m['exp']} лет, специализация: {m['spec']}")

    lines += [
        "",
        "Если вопрос не о салоне — вежливо скажи что отвечаешь только на вопросы о салоне.",
        "Язык ответа — русский. Отвечай в 2-4 предложения максимум.",
    ]

    return "\n".join(lines)
