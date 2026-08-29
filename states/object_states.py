"""FSM-состояния для сценариев 'Добавить объект' и 'Редактировать объект'
(handlers/admin_add_object.py, handlers/admin_manage_objects.py, только админы)."""
from aiogram.fsm.state import State, StatesGroup


class AddObjectForm(StatesGroup):
    waiting_title = State()
    waiting_object_photos = State()   # 1. фото объекта (сразу после названия)
    waiting_entry_photos = State()    # 2. фото залаза (точки входа)
    waiting_history = State()
    waiting_current_state = State()
    waiting_rumors = State()
    waiting_coordinates = State()     # 3. координаты (сразу после слухов)
    waiting_min_credits = State()
    waiting_danger_level = State()    # обязательный выбор одной из 5 кнопок — без пропуска
    confirm = State()


class EditObjectForm(StatesGroup):
    """Редактирование существующего объекта. Какой объект/поле редактируется —
    хранится в data FSM (object_id, field / photo_kind)."""
    waiting_value = State()   # data: object_id, field
    waiting_photos = State()  # data: object_id, photo_kind ('object'|'entry')
