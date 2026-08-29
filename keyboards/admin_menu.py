"""keyboards/admin_menu.py — клавиатуры админ-панели, сценария 'Добавить объект'
и сценариев управления уже существующими объектами (handlers/admin_manage_objects.py):
редактирование полей/фото и удаление с двумя подтверждениями."""
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config

# Текстовые/числовые поля объекта, доступные для редактирования по одному —
# (имя колонки в БД, подпись кнопки). Порядок как в форме добавления.
# danger_level сюда не входит — у него отдельная кнопка и клавиатура из 5
# вариантов (danger_level_pick_kb), а не свободный текстовый ввод.
EDITABLE_TEXT_FIELDS: list[tuple[str, str]] = [
    ("title", "📝 Название"),
    ("history", "📜 История"),
    ("current_state", "🏗 Состояние"),
    ("rumors", "👂 Слухи"),
    ("coordinates", "📍 Координаты"),
    ("min_credits", "🔒 Порог доступа"),
]


def admin_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить объект", callback_data="admin:add_object")
    builder.button(text="📂 Объекты архива", callback_data="admin:objects")
    builder.button(text="📋 Ожидающие инсайды", callback_data="admin:pending")
    builder.button(text="🧪 Изменить свои кредиты", callback_data="admin:set_own_credits")
    builder.adjust(1)
    return builder.as_markup()


def danger_level_pick_kb(callback_prefix: str) -> InlineKeyboardMarkup:
    """5 кнопок выбора уровня опасности (config.DANGER_LEVELS). Вызывающий
    код передаёт свой callback_prefix и сам разбирает код уровня из
    последнего сегмента callback_data:
    - при добавлении нового объекта: prefix="adddanger" -> "adddanger:<code>"
      (объект ещё не создан, id хранится в FSM-состоянии, не нужен в callback_data);
    - при редактировании существующего: prefix=f"objdanger:{object_id}"
      -> "objdanger:<id>:<code>"."""
    builder = InlineKeyboardBuilder()
    for code, label, emoji in config.DANGER_LEVELS:
        builder.button(text=f"{emoji} {label}", callback_data=f"{callback_prefix}:{code}")
    builder.adjust(1)
    return builder.as_markup()


def add_object_photos_done_kb(stage: str) -> InlineKeyboardMarkup:
    """stage: 'object' или 'entry' — какую серию фото сейчас собираем."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Готово", callback_data=f"objphoto:{stage}:done")
    return builder.as_markup()


def add_object_confirm_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Сохранить в архив", callback_data="objconfirm:save")
    builder.button(text="❌ Отмена", callback_data="objconfirm:cancel")
    builder.adjust(2)
    return builder.as_markup()


def admin_objects_list_kb(objects) -> InlineKeyboardMarkup:
    """Список всех объектов архива (любой статус) для управления —
    редактирования или удаления. Черновики помечены иконкой 📝, чтобы
    отличать их от опубликованных 🗂 объектов."""
    builder = InlineKeyboardBuilder()
    for obj in objects:
        icon = "📝" if obj["status"] == "draft" else "🗂"
        builder.button(text=f"{icon} {obj['title']}", callback_data=f"adminobj:{obj['id']}")
    builder.button(text="🔙 В админ-панель", callback_data="admin:menu")
    builder.adjust(1)
    return builder.as_markup()


def admin_object_manage_kb(object_id: int) -> InlineKeyboardMarkup:
    """Карточка одного объекта в режиме управления: редактировать / удалить / назад."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Редактировать", callback_data=f"adminobj:{object_id}:edit")
    builder.button(text="🗑 Удалить объект", callback_data=f"adminobj:{object_id}:delete")
    builder.button(text="🔙 К списку объектов", callback_data="admin:objects")
    builder.adjust(1)
    return builder.as_markup()


def edit_object_fields_kb(object_id: int) -> InlineKeyboardMarkup:
    """Выбор, какое поле объекта редактировать. Фото объекта/залаза
    редактируются отдельно от текстовых полей — у них своя мини-форма
    (см. edit_photos_kb) с добавлением по очереди, как при добавлении объекта."""
    builder = InlineKeyboardBuilder()
    for field, label in EDITABLE_TEXT_FIELDS:
        builder.button(text=label, callback_data=f"objedit:{object_id}:{field}")
    builder.button(text="⚠️ Уровень опасности", callback_data=f"objdanger:{object_id}")
    builder.button(text="📸 Фото объекта", callback_data=f"objedit:{object_id}:object_photos")
    builder.button(text="🚪 Фото залаза", callback_data=f"objedit:{object_id}:entry_photos")
    builder.button(text="🔙 Назад", callback_data=f"adminobj:{object_id}")
    builder.adjust(1)
    return builder.as_markup()


def edit_photos_kb(object_id: int, kind: str) -> InlineKeyboardMarkup:
    """Клавиатура во время загрузки новых фото при редактировании: можно
    сначала очистить старый набор (чтобы заменить целиком), а когда новые
    фото прикреплены — завершить."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Очистить старые фото", callback_data=f"objeditphoto:{object_id}:{kind}:clear")
    builder.button(text="✅ Готово", callback_data=f"objeditphoto:{object_id}:{kind}:done")
    builder.adjust(1)
    return builder.as_markup()


def delete_object_confirm_kb(object_id: int) -> InlineKeyboardMarkup:
    """Первый шаг подтверждения удаления объекта — случайное нажатие
    «Удалить объект» на карточке ещё ничего не стирает."""
    builder = InlineKeyboardBuilder()
    builder.button(text="⚠️ Да, продолжить", callback_data=f"objdel:{object_id}:confirm1")
    builder.button(text="Отмена", callback_data=f"adminobj:{object_id}")
    builder.adjust(1)
    return builder.as_markup()


def delete_object_final_confirm_kb(object_id: int) -> InlineKeyboardMarkup:
    """Второй, финальный шаг подтверждения — только после него объект
    реально удаляется из БД."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Да, удалить навсегда", callback_data=f"objdel:{object_id}:confirm2")
    builder.button(text="Отмена", callback_data=f"adminobj:{object_id}")
    builder.adjust(1)
    return builder.as_markup()
