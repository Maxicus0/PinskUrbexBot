"""utils/danger_levels.py — справочник уровней опасности объектов архива.

Сами уровни (код, подпись, эмодзи) заданы в config.DANGER_LEVELS, по
возрастанию серьёзности. 'black' формально идёт последним, но по смыслу
это не "опаснее красного", а отдельный статус "мало данных для оценки" —
так и озаглавлен в config.DANGER_LEVELS.
"""
import config

_BY_CODE: dict[str, tuple[str, str]] = {
    code: (emoji, label) for code, label, emoji in config.DANGER_LEVELS
}
_FALLBACK = _BY_CODE[config.DEFAULT_DANGER_LEVEL]


def danger_emoji(code: str | None) -> str:
    return _BY_CODE.get(code, _FALLBACK)[0]


def danger_label(code: str | None) -> str:
    return _BY_CODE.get(code, _FALLBACK)[1]


def danger_line(code: str | None) -> str:
    """Строка для карточки объекта, напр. '🟢 Тихо зашли и гуляйте'."""
    emoji, label = _BY_CODE.get(code, _FALLBACK)
    return f"{emoji} {label}"
