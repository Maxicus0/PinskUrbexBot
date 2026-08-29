"""FSM-состояния для служебных действий админа (handlers/admin_panel.py)."""
from aiogram.fsm.state import State, StatesGroup


class AdminSelfCreditsForm(StatesGroup):
    # Ожидание нового значения кредитов доверия (любое целое, для тестов) —
    # см. handlers/admin_panel.py: start_set_own_credits / apply_set_own_credits.
    waiting_value = State()
