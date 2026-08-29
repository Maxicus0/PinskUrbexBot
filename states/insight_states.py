"""FSM-состояния для сценария 'Отправить инсайд' (handlers/insight_submit.py)."""
from aiogram.fsm.state import State, StatesGroup


class InsightForm(StatesGroup):
    waiting_content = State()          # первое сообщение: текст ИЛИ фото/видео (с подписью или без)
    waiting_text_after_media = State() # медиа пришло без подписи — дозапрашиваем текст
    waiting_media = State()            # сбор доп. фото/видео (до config.MAX_INSIGHT_MEDIA), затем «Готово»
    confirm = State()
