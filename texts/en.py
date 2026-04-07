"""All bot texts in English."""

EN = {
    # ── Start ──────────────────────────────────────────────
    "welcome": (
        "👋 Hello, <b>{name}</b>!\n\n"
        "I'm the <b>{salon_name}</b> bot.\n"
        "I'll help you book an appointment or answer any questions."
    ),
    "welcome_back": (
        "Welcome back, <b>{name}</b>! 👋\n\n"
        "How can I help you today?"
    ),
    "main_menu_text": "✨ <b>{salon_name}</b>\n\nChoose a section 👇",

    # ── Main menu ──────────────────────────────────────────
    "main_menu": "📋 Main menu",

    # ── Settings ───────────────────────────────────────────
    "settings_title": "<b>⚙️ Settings</b>\n\nChoose what you want to change:",
    "settings_saved": "✅ <b>Settings saved</b>",
    "settings_lang_prompt": "🌐 <b>Choose language:</b>",

    # ── Profile ────────────────────────────────────────────
    "profile_title": (
        "<b>👤 Profile</b>\n\n"
        "🆔 ID: <code>{user_id}</code>\n"
        "📛 Name: <b>{name}</b>\n"
        "🌐 Language: <code>{lang}</code>\n"
        "📅 Registered: <i>{created_at}</i>"
    ),

    # ── Help ───────────────────────────────────────────────
    "help_title": (
        "<b>ℹ️ Help</b>\n\n"
        "Use the menu buttons to navigate.\n\n"
        "Support: <code>@support</code>"
    ),

    # ── Navigation ─────────────────────────────────────────
    "back": "◀️ Back",
    "cancel": "❌ Cancel",
    "confirm": "✅ Confirm",

    # ── Errors ─────────────────────────────────────────────
    "error_unknown": "⚠️ Something went wrong. Please try again.",
    "error_not_text": "📝 Please send a text message.",

    # ── Buttons ────────────────────────────────────────────
    "btn_main_menu":  "🏠 Main menu",
    "btn_settings":   "⚙️ Settings",
    "btn_profile":    "👤 Profile",
    "btn_help":       "ℹ️ Help",
    "btn_lang":       "🌐 Language: {lang}",
    "btn_back":       "◀️ Back to menu",

    # ── About ──────────────────────────────────────────────
    "about": (
        "🏠 <b>{salon_name}</b>\n\n"
        "📍 {salon_address}\n"
        "   {salon_metro}\n\n"
        "⏰ <b>Working hours:</b>\n"
        "   {salon_hours_weekdays}\n"
        "   {salon_hours_weekends}\n\n"
        "📞 {salon_phone}\n"
        "📸 {salon_instagram}\n\n"
        "✨ We have been working since <b>{salon_since}</b>.\n"
        "Our masters are certified specialists with 4+ years of experience."
    ),

    # ── Services ───────────────────────────────────────────
    "services_menu": "💅 <b>Services & prices</b>\n\nChoose a category:",

    # ── Booking ────────────────────────────────────────────
    "booking_choose_category": "📅 <b>Book an appointment</b>\n\nChoose a service category:",
    "booking_choose_service":  "Choose a service:",
    "booking_choose_master":   "👤 Choose a master:",
    "booking_enter_datetime": (
        "📅 <b>Enter preferred date and time</b>\n\n"
        "Write freely, for example:\n"
        "<i>tomorrow at 15:00</i>\n"
        "<i>Friday 12:30</i>\n"
        "<i>April 3 at 11:00</i>"
    ),
    "booking_enter_phone": (
        "📞 <b>Enter your phone number</b>\n\n"
        "For example: <i>+44 7700 900000</i>"
    ),
    "booking_confirm": (
        "✅ <b>Confirm booking:</b>\n\n"
        "💅 Service: <b>{service}</b>\n"
        "👤 Master: <b>{master}</b>\n"
        "📅 Date/time: <b>{date_time}</b>\n"
        "📞 Phone: <b>{phone}</b>"
    ),
    "booking_success": (
        "🎉 <b>Booking confirmed!</b>\n\n"
        "We will contact you to confirm.\n"
        "📞 To change — call us: {salon_phone}"
    ),
    "booking_cancelled": "❌ Booking cancelled. Returning to main menu.",

    # ── My bookings ────────────────────────────────────────
    "my_bookings_empty": (
        "📋 <b>My bookings</b>\n\n"
        "You have no bookings yet.\n"
        "Tap «📅 Book» to make an appointment!"
    ),
    "my_bookings_header": "📋 <b>My bookings</b>\n",

    # ── AI chat ────────────────────────────────────────────
    "ai_chat_prompt": (
        "🤖 <b>AI Assistant — {salon_name}</b>\n\n"
        "Ask any question about services, prices, masters or booking."
    ),
    "ai_chat_thinking": "⏳ Thinking...",
    "ai_chat_unavailable": (
        "😔 AI is temporarily unavailable.\n"
        "Please call us: <b>{salon_phone}</b>"
    ),
    "ai_chat_error": (
        "⚠️ Could not get a response. Please try again\n"
        "or call: <b>{salon_phone}</b>"
    ),

    # ── Admin notification ─────────────────────────────────
    "admin_new_booking": (
        "📅 <b>New booking!</b>\n\n"
        "👤 Client: {user_name} ({username})\n"
        "💅 Service: {service}\n"
        "👨‍🎨 Master: {master}\n"
        "🕐 Date/time: {date_time}\n"
        "📞 Phone: {phone}\n"
        "🆔 Booking ID: #{booking_id}"
    ),

    # ── GDPR ───────────────────────────────────────────────
    "gdpr_title": (
        "🔒 <b>Privacy & Data</b>\n\n"
        "To use this bot, we need to store your name and contact details "
        "for appointment booking purposes.\n\n"
        "• We do not share your data with third parties\n"
        "• You can delete your data at any time via Profile\n"
        "• Data is stored securely on our server\n\n"
        "Please confirm to continue."
    ),
    "gdpr_accept_btn": "✅ I agree",
    "gdpr_decline_btn": "❌ Decline",
    "gdpr_declined": (
        "You declined. The bot cannot be used without data consent.\n"
        "If you change your mind, send /start again."
    ),
    "gdpr_delete_confirm": (
        "⚠️ <b>Delete my data</b>\n\n"
        "This will anonymise all your personal data (name, phone, birthday).\n"
        "Your booking history will remain but won't be linked to you.\n\n"
        "Are you sure?"
    ),
    "gdpr_deleted": "✅ Your personal data has been deleted.",
}
