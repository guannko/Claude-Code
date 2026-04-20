from . import (
    start, admin, admin_schedule, admin_masters, admin_masters_mgmt,
    admin_settings, admin_services, admin_license,
    master_panel, master_registration, masters_flow, navigation,
    booking, client_bookings, ai_chat,
    reviews, gallery, admin_broadcast, admin_reports,
    master_clients, master_day,
    common,
)

# Порядок важен: common (fallback) — всегда последним
all_routers = [
    start.router,
    admin.router,
    admin_schedule.router,
    admin_masters.router,
    admin_masters_mgmt.router,
    admin_settings.router,
    admin_services.router,
    admin_license.router,          # ← лицензия
    master_day.router,
    master_clients.router,
    master_panel.router,
    master_registration.router,
    masters_flow.router,
    booking.router,
    client_bookings.router,
    navigation.router,
    ai_chat.router,
    reviews.router,
    gallery.router,
    admin_broadcast.router,
    admin_reports.router,
    common.router,                 # ← ПОСЛЕДНИМ
]

__all__ = ["all_routers"]
