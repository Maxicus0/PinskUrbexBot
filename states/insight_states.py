"""FSM-состояния для сценария 'Отправить инсайд' (handlers/insight_submit.py)."""
from aiogram.fsm.state import State, StatesGroup


class InsightForm(StatesGroup):
    waiting_content = State()          # первое сообщение: текст ИЛИ фото с подписью
    waiting_text_after_photo = State() # фото пришло без подписи — дозапрашиваем текст
    waiting_photo_optional = State()   # текст уже есть — предлагаем опционально приложить фото
    confirm = State()
