"""
Все FSM-состояния бота в одном месте.
Добавляй новые StatesGroup сюда по мере роста бота.
"""

from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    entering_name = State()


class SettingsStates(StatesGroup):
    """Состояния для изменения настроек."""
    choosing_lang = State()


# ── Запись на приём ───────────────────────────────────────

class BookingStates(StatesGroup):
    choosing_category = State()
    choosing_service = State()
    choosing_master = State()
    entering_datetime = State()
    entering_phone = State()
    confirming_phone = State()
    confirming = State()


# ── AI-чат ────────────────────────────────────────────────

class AiChatStates(StatesGroup):
    waiting_question = State()


# ── Управление расписанием (для администратора) ───────────

class AdminScheduleStates(StatesGroup):
    entering_hours = State()   # ввод "10:00-20:00"
    entering_dayoff = State()  # ввод даты "15.04.2026"
    entering_reason = State()  # (опционально) причина выходного


# ── Флоу записи через мастеров ────────────────────────────

class MasterFlowStates(StatesGroup):
    waiting_phone = State()      # ввод телефона в мастер-флоу
    confirming_phone = State()   # подтверждение сохранённого телефона


# ── Регистрация мастера ───────────────────────────────────

class MasterRegStates(StatesGroup):
    waiting_code = State()     # ввод кода при /master регистрации


# ── Управление администраторами ───────────────────────────

class AdminStates(StatesGroup):
    entering_admin_id = State()        # ввод user_id нового админа
    uploading_master_photo = State()   # загрузка фото мастера
    # Master management
    master_editing_name = State()
    master_editing_description = State()
    master_editing_tg = State()
    master_adding_name = State()
    master_adding_category = State()


# ── Отзывы ────────────────────────────────────────────────

class ReviewStates(StatesGroup):
    waiting_comment = State()


# ── Галерея работ ─────────────────────────────────────────

class GalleryStates(StatesGroup):
    choosing_category = State()
    uploading_photo = State()
    entering_caption = State()


# ── Рассылка ─────────────────────────────────────────────

class BroadcastStates(StatesGroup):
    entering_message = State()
    confirming = State()


# ── Мастер: заметки о клиентах ────────────────────────────

class MasterNotesStates(StatesGroup):
    entering_note = State()


# ── Профиль: день рождения ───────────────────────────────

class ProfileStates(StatesGroup):
    entering_birthdate = State()


# ── Мастер: управление слотами дня ───────────────────────

class MasterDayStates(StatesGroup):
    entering_slot_time = State()   # ввод времени "HH:MM"


# ── Настройки салона (для администратора) ─────────────────

class AdminSettingsStates(StatesGroup):
    entering_value = State()   # ввод нового значения настройки
