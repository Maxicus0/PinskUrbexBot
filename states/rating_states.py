"""FSM-состояния для оценки инсайда админом (handlers/admin_rate_insight.py)."""
from aiogram.fsm.state import State, StatesGroup


class RateInsightForm(StatesGroup):
    waiting_rating = State()          # ожидание числа 0-config.MAX_INSIGHT_CREDITS, присланного админом в чат
    waiting_reject_reason = State()   # 0 кредитов -> обязательная причина отказа, уходит автору инсайда
    waiting_note = State()            # ожидание (опциональной) заметки об авторе после оценки, data: user_id
