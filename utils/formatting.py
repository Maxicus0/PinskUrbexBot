"""
utils/formatting.py — сборка текстов сообщений (карточки объектов, уведомления,
карточка уровня доверия), склонение слова "кредит".

Бот работает с ParseMode.HTML, поэтому любой пользовательский текст перед
вставкой в сообщение обязан проходить через esc().
"""
from html import escape

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


def format_object_teaser(obj_row, user_credits: int) -> str:
    """Короткая подпись объекта для кнопки в списке архива.

    Если кредитов не хватает — название объекта НЕ показывается вообще
    (чтобы не палить, что за объект скрыт), вместо него — сколько кредитов
    доверия нужно набрать, например «🔒 10 кредитов доверия». Открытые
    объекты показываются с названием под общей иконкой архива 🗂."""
    need = obj_row["min_credits"]
    locked = user_credits < need
    if locked:
        return f"🔒 {need} {plural_credits(need)} доверия"
    pin = " 📍" if obj_row["coordinates"] else ""
    return f"🗂 {obj_row['title']}{pin}"


def format_object_card(obj_row) -> str:
    """Полная карточка объекта: история/состояние/слухи/координаты."""
    parts = [f"🗂 <b>{esc(obj_row['title'])}</b>"]

    coords = obj_row["coordinates"]
    if coords:
        maps_url = coordinates_to_maps_url(coords)
        if maps_url:
            parts.append(f"\n📍 <b>Координаты</b>\n{esc(coords)} — <a href=\"{maps_url}\">открыть в Google Maps</a>")
        else:
            parts.append(f"\n📍 <b>Координаты</b>\n{esc(coords)}")

    if obj_row["history"]:
        parts.append(f"\n📜 <b>История</b>\n{esc(obj_row['history'])}")
    if obj_row["current_state"]:
        parts.append(f"\n🏗 <b>Нынешнее состояние</b>\n{esc(obj_row['current_state'])}")
    if obj_row["rumors"]:
        parts.append(f"\n👂 <b>Слухи</b>\n{esc(obj_row['rumors'])}")

    return "\n".join(parts)


def format_insight_notification(insight_row) -> str:
    """Текст уведомления, которое уходит админам при поступлении нового инсайда.

    Намеренно НЕ содержит информации об авторе (ни username, ни имени, ни
    telegram_id) — инсайд должен оцениваться полностью анонимно, чтобы
    исключить кумовство и предвзятость админов к конкретным пользователям.
    Автор всё равно корректно получает кредиты после оценки — user_id
    хранится в БД (insights.user_id), просто не показывается в карточке."""
    lines = [
        f"💡 <b>Новый инсайд #{insight_row['id']}</b>",
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
