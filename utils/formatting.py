"""
utils/formatting.py — сборка текстов сообщений (карточки объектов, уведомления,
карточка уровня доверия), склонение слова "кредит".

Бот работает с ParseMode.HTML, поэтому любой пользовательский текст перед
вставкой в сообщение обязан проходить через esc() — единственное исключение
это поля с поддержкой форматирования (история/состояние/слухи объекта), см.
rich_text_or_none().
"""
from html import escape

from aiogram.types import Message

import config
from utils.danger_levels import danger_emoji, danger_line
from utils.levels import get_level_info, progress_bar
from utils.validators import coordinates_to_maps_url

# Лимит Telegram на caption у фото/медиагруппы. При превышении Telegram не
# обрежет текст сам, а вернёт ошибку — поэтому длинные карточки объектов
# отправляются отдельным текстовым сообщением, а не в подписи к фото
# (см. handlers/archive.py).
CAPTION_LIMIT = 1024


def esc(value) -> str:
    """HTML-экранирование произвольного пользовательского текста перед вставкой
    в сообщение с ParseMode.HTML. Всегда возвращает строку (None -> "")."""
    if value is None:
        return ""
    return escape(str(value), quote=False)


def rich_text_or_none(message: Message) -> str | None:
    """Достаёт значение полей со свободным форматированием — история,
    нынешнее состояние, слухи (см. handlers/admin_add_object.py,
    handlers/admin_manage_objects.py).

    Вместо plain message.text берётся message.html_text — aiogram сам
    конвертирует entities сообщения (жирный, курсив, зачёркнутый, подчёрк-
    нутый, спойлер, моноширинный, ссылки и т.п. — всё, что админ применил
    через стандартное форматирование в клиенте Telegram, включая
    markdown-подобный ввод вроде *жирный*/_курсив_, который клиент сам
    превращает в entity на лету) в готовый HTML с уже экранированным
    текстом внутри тегов. Поэтому результат этой функции можно вставлять в
    сообщение с ParseMode.HTML напрямую, БЕЗ повторного esc() — двойное
    экранирование сломает теги.

    Как и раньше, «-» очищает поле (возвращает None)."""
    plain = (message.text or "").strip()
    if plain == "-":
        return None
    html = (message.html_text or "").strip()
    return html or None


def plural_credits(n: int) -> str:
    """Возвращает 'кредит' / 'кредита' / 'кредитов' по правилам русского языка."""
    n_abs = abs(n) % 100
    n1 = n_abs % 10
    if 11 <= n_abs <= 14:
        return "кредитов"
    if n1 == 1:
        return "кредит"
    if 2 <= n1 <= 4:
        return "кредита"
    return "кредитов"


def format_object_teaser(
    obj_row, user_credits: int, display_mode: str = config.DEFAULT_ARCHIVE_DISPLAY_MODE
) -> str:
    """Короткая подпись объекта для кнопки в списке архива.

    Если кредитов не хватает — название объекта НЕ показывается вообще
    (чтобы не палить, что за объект скрыт), вместо него — сколько кредитов
    доверия нужно набрать, например «🔒 Порог доступа: 10 кредитов доверия».
    Это поведение не зависит от display_mode — риск и название закрытого
    объекта не палятся заранее в любом режиме.

    Открытые объекты показываются как «{icon} Название», где icon зависит
    от личной настройки пользователя (см. /settings, config.ARCHIVE_DISPLAY_MODES):
    - "standard" (по умолчанию) — общая иконка архива 🗂, без эмодзи уровня
      опасности (⚪🟢🟡🔴⚫, см. config.DANGER_LEVELS): риск не палится
      заранее прямо на кнопке, он виден только внутри самой карточки объекта
      (см. format_object_card);
    - "danger_color" — вместо 🗂 подставляется эмодзи фактического уровня
      опасности объекта (utils.danger_levels.danger_emoji).

    Если у объекта известны координаты — рядом всегда стоит 📍, независимо
    от того, открыт объект или скрыт замочком, и независимо от display_mode."""
    need = obj_row["min_credits"]
    locked = user_credits < need
    pin = " 📍" if obj_row["coordinates"] else ""
    if locked:
        return f"🔒 Порог доступа: {need} {plural_credits(need)} доверия{pin}"
    icon = danger_emoji(obj_row["danger_level"]) if display_mode == "danger_color" else "🗂"
    return f"{icon} {obj_row['title']}{pin}"


def format_object_card(obj_row) -> str:
    """Полная карточка объекта: история/состояние/слухи/координаты, уровень
    опасности.

    Блок уровня опасности («⚠️ Уровень опасности объекта» + сама строка)
    отображается последним блоком карточки — с отступом в два переноса
    строки (как и остальные блоки, см. ниже) от «Нынешнее состояние», если
    слухов нет, либо от «Слухи», если они есть (он всегда добавляется в
    parts последним, а перед ним последним по факту оказывается то из двух
    полей, что заполнено).

    История/состояние/слухи не эскейпятся через esc() — эти поля хранят уже
    готовый HTML с поддержкой форматирования (жирный, курсив и т.п., см.
    rich_text_or_none()), где текст внутри тегов экранирован заранее."""
    parts = [f"🗂 <b>{esc(obj_row['title'])}</b>"]

    coords = obj_row["coordinates"]
    if coords:
        maps_url = coordinates_to_maps_url(coords)
        if maps_url:
            parts.append(f"\n📍 <b>Координаты</b>\n{esc(coords)} — <a href=\"{maps_url}\">открыть в Google Maps</a>")
        else:
            parts.append(f"\n📍 <b>Координаты</b>\n{esc(coords)}")

    if obj_row["history"]:
        parts.append(f"\n📜 <b>История</b>\n{obj_row['history']}")
    if obj_row["current_state"]:
        parts.append(f"\n🏗 <b>Нынешнее состояние</b>\n{obj_row['current_state']}")
    if obj_row["rumors"]:
        parts.append(f"\n👂 <b>Слухи</b>\n{obj_row['rumors']}")

    parts.append(f"\n⚠️ <b>Уровень опасности объекта</b>\n{danger_line(obj_row['danger_level'])}")

    return "\n".join(parts)


def format_insight_notification(insight_row, queue_number: int) -> str:
    """Текст уведомления, которое уходит админам при поступлении нового инсайда.

    Намеренно НЕ содержит информации об авторе (ни username, ни имени, ни
    telegram_id) — инсайд должен оцениваться полностью анонимно, чтобы
    исключить кумовство и предвзятость админов к конкретным пользователям.
    Автор всё равно корректно получает кредиты после оценки — user_id
    хранится в БД (insights.user_id), просто не показывается в карточке.

    queue_number — позиция инсайда в очереди ожидающих (1, 2, 3…), а НЕ его
    id из БД: id — сквозной счётчик по всей истории и сам по себе выдал бы,
    сколько инсайдов всего когда-либо подано (см.
    database.insights_repo.get_queue_position)."""
    lines = [
        f"💡 <b>Новый инсайд #{queue_number}</b>",
        "",
        esc(insight_row["text"]),
    ]
    return "\n".join(lines)


def format_level_card(credits: int) -> str:
    """Карточка уровня доверия: название, цвет, полоска прогресса до следующего уровня."""
    info = get_level_info(credits)
    bar = progress_bar(info.progress_fraction)

    lines = [
        f"{info.color} <b>Уровень {info.index}: {info.name}</b>",
        "",
        f"[{bar}]",
        f"💳 Кредитов доверия: <b>{credits}</b>",
    ]

    if info.is_max:
        lines.append("\n🏆 Максимальный уровень доверия. Ты — легенда архива.")
    else:
        left = info.credits_to_next
        lines.append(
            f"\n➡️ До уровня «{info.next_name}» осталось <b>{left}</b> "
            f"{plural_credits(left)} ({credits}/{info.next_threshold})"
        )

    return "\n".join(lines)
