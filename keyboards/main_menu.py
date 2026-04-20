"""Инлайн-клавиатуры главного меню. Кнопки переопределяются через настройки БД."""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def _setting(key: str) -> str:
    """Синхронное чтение из кэша настроек (не обращается к БД)."""
    try:
        from database.db import _settings_cache
        return _settings_cache.get(key, "")
    except Exception:
        return ""


# Дефолтные подписи кнопок
_BTN_DEFAULT = {
    "ru": {
        "services":    "💅 Услуги и цены",
        "book":        "📅 Записаться",
        "masters":     "👤 Специалисты",
        "gallery":     "🖼 Галерея работ",
        "ai":          "🤖 AI-помощник",
        "about":       "📍 О нас",
        "mybookings":  "📋 Мои записи",
        "profile":     "👤 Профиль",
        "panel":       "⚙️ Панель",
    },
    "en": {
        "services":    "💅 Services & prices",
        "book":        "📅 Book appointment",
        "masters":     "👤 Specialists",
        "gallery":     "🖼 Gallery",
        "ai":          "🤖 AI assistant",
        "about":       "📍 About us",
        "mybookings":  "📋 My bookings",
        "profile":     "👤 Profile",
        "panel":       "⚙️ Admin panel",
    },
}


def _b(key: str, lang: str) -> str:
    """Возвращает подпись кнопки: сначала кастомная из настроек, потом дефолт."""
    custom = _setting(f"btn_{key}")
    if custom:
        return custom
    return _BTN_DEFAULT.get(lang, _BTN_DEFAULT["ru"]).get(
        key, _BTN_DEFAULT["ru"].get(key, key)
    )


def main_menu_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    lang_toggle = "🌐 EN" if lang == "ru" else "🌐 RU"
    lang_target = "en" if lang == "ru" else "ru"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=_b("services",   lang), callback_data="menu:services")],
        [InlineKeyboardButton(text=_b("book",       lang), callback_data="book:start")],
        [InlineKeyboardButton(text=_b("masters",    lang), callback_data="menu:masters")],
        [InlineKeyboardButton(text=_b("gallery",    lang), callback_data="gallery:browse")],
        [InlineKeyboardButton(text=_b("ai",         lang), callback_data="menu:ai_chat")],
        [InlineKeyboardButton(text=_b("about",      lang), callback_data="menu:about")],
        [InlineKeyboardButton(text=_b("mybookings", lang), callback_data="menu:my_bookings")],
        [
            InlineKeyboardButton(text=_b("profile", lang), callback_data="menu:profile"),
            InlineKeyboardButton(text=lang_toggle,         callback_data=f"lang:toggle:{lang_target}"),
        ],
    ])


_ADM_BTN = {
    "ru": {
        "new_bookings":  "🟡 Новые записи",
        "all_bookings":  "📋 Все записи",
        "clients":       "👥 Клиенты",
        "stats":         "📊 Статистика",
        "masters":       "👩‍🎨 Мастера",
        "master_photos": "📸 Фото мастеров",
        "schedule":      "📅 Расписание",
        "gallery":       "🖼 Галерея",
        "broadcast":     "📣 Рассылка",
        "reports":       "📈 Отчёты",
        "settings":      "⚙️ Настройки",
        "svc_mgmt":      "💅 Услуги (ред.)",
        "admins":        "👑 Администраторы",
        "history":       "📋 История",
        "client_view":   "👤 Клиентское меню",
        "license":       "🔑 Лицензия",
    },
    "en": {
        "new_bookings":  "🟡 New bookings",
        "all_bookings":  "📋 All bookings",
        "clients":       "👥 Clients",
        "stats":         "📊 Statistics",
        "masters":       "👩‍🎨 Masters",
        "master_photos": "📸 Master photos",
        "schedule":      "📅 Schedule",
        "gallery":       "🖼 Gallery",
        "broadcast":     "📣 Broadcast",
        "reports":       "📈 Reports",
        "settings":      "⚙️ Settings",
        "svc_mgmt":      "💅 Services (edit)",
        "admins":        "👑 Administrators",
        "history":       "📋 History",
        "client_view":   "👤 Client menu",
        "license":       "🔑 License",
    },
}


def admin_panel_kb(is_owner: bool = False, lang: str = "ru") -> InlineKeyboardMarkup:
    a = _ADM_BTN.get(lang, _ADM_BTN["ru"])
    rows = [
        [
            InlineKeyboardButton(text=a["new_bookings"],  callback_data="adm:bookings_new"),
            InlineKeyboardButton(text=a["all_bookings"],  callback_data="adm:bookings_all"),
        ],
        [
            InlineKeyboardButton(text=a["clients"],       callback_data="adm:users"),
            InlineKeyboardButton(text=a["stats"],         callback_data="adm:stats"),
        ],
        [
            InlineKeyboardButton(text=a["masters"],       callback_data="adm:masters"),
            InlineKeyboardButton(text=a["master_photos"], callback_data="admin:master_photos"),
        ],
        [
            InlineKeyboardButton(text=a["schedule"],      callback_data="adm_sch:list"),
            InlineKeyboardButton(text=a["gallery"],       callback_data="gallery:admin"),
        ],
        [
            InlineKeyboardButton(text=a["broadcast"],     callback_data="broadcast:start"),
            InlineKeyboardButton(text=a["reports"],       callback_data="reports:menu"),
        ],
        [
            InlineKeyboardButton(text=a["settings"],      callback_data="adm_cfg:menu"),
            InlineKeyboardButton(text=a["svc_mgmt"],      callback_data="adm_svc:list"),
        ],
        [
            InlineKeyboardButton(text=a["history"],       callback_data="adm:history"),
            InlineKeyboardButton(text=a["license"],       callback_data="license:menu"),
        ],
    ]
    if is_owner:
        rows.append([
            InlineKeyboardButton(text=a["admins"],        callback_data="admin:admins"),
        ])
    lang_toggle = "🌐 EN" if lang == "ru" else "🌐 RU"
    lang_target = "en" if lang == "ru" else "ru"
    rows.append([
        InlineKeyboardButton(text=a["client_view"],       callback_data="adm:client_view"),
        InlineKeyboardButton(text=lang_toggle,            callback_data=f"lang:toggle:{lang_target}"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_menu_with_admin_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    lang_toggle = "🌐 EN" if lang == "ru" else "🌐 RU"
    lang_target = "en" if lang == "ru" else "ru"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=_b("services",   lang), callback_data="menu:services")],
        [InlineKeyboardButton(text=_b("book",       lang), callback_data="book:start")],
        [InlineKeyboardButton(text=_b("masters",    lang), callback_data="menu:masters")],
        [InlineKeyboardButton(text=_b("gallery",    lang), callback_data="gallery:browse")],
        [InlineKeyboardButton(text=_b("ai",         lang), callback_data="menu:ai_chat")],
        [InlineKeyboardButton(text=_b("about",      lang), callback_data="menu:about")],
        [InlineKeyboardButton(text=_b("mybookings", lang), callback_data="menu:my_bookings")],
        [
            InlineKeyboardButton(text=_b("profile", lang), callback_data="menu:profile"),
            InlineKeyboardButton(text=lang_toggle,         callback_data=f"lang:toggle:{lang_target}"),
        ],
        [InlineKeyboardButton(text=_b("panel",      lang), callback_data="adm:panel")],
    ])


def master_panel_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    lang_toggle = "🌐 EN" if lang == "ru" else "🌐 RU"
    lang_target = "en" if lang == "ru" else "ru"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Мои записи",          callback_data="mst_panel:bookings")],
        [InlineKeyboardButton(text="🗓 Мой день",             callback_data="mst_day:home")],
        [InlineKeyboardButton(text="📅 Недельное расписание", callback_data="mst_panel:schedule")],
        [InlineKeyboardButton(text="👥 Мои клиенты",          callback_data="mst_clients:list")],
        [InlineKeyboardButton(text="🖼 Добавить в галерею",   callback_data="gallery:master_upload")],
        [
            InlineKeyboardButton(text="👤 Клиентское меню",  callback_data="adm:client_view"),
            InlineKeyboardButton(text=lang_toggle,           callback_data=f"lang:toggle:{lang_target}"),
        ],
    ])
