"""
utils/validators.py
----------------------
Валидация и разбор координат, которые админ копирует из Google Maps в
формате градусы/минуты/секунды, например:
    52°07'56.1"N 26°01'02.5"E

Формат жёсткий (широта с N/S, долгота с E/W, именно в таком порядке —
как его и отдаёт Google Maps при копировании), но нечувствителен к
регистру букв стран света и лишним пробелам.
"""
import re

_COORD_RE = re.compile(
    r"""^\s*
    (?P<lat_deg>\d{1,3})°\s*(?P<lat_min>\d{1,2})'\s*(?P<lat_sec>\d{1,2}(?:\.\d+)?)"\s*(?P<lat_dir>[NSns])
    \s*[,\s]\s*
    (?P<lon_deg>\d{1,3})°\s*(?P<lon_min>\d{1,2})'\s*(?P<lon_sec>\d{1,2}(?:\.\d+)?)"\s*(?P<lon_dir>[EWew])
    \s*$""",
    re.VERBOSE,
)


def is_valid_coordinates(text: str) -> bool:
    return bool(_COORD_RE.match(text.strip()))


def normalize_coordinates(text: str) -> str | None:
    """Приводит N/E/S/W к верхнему регистру. None, если формат не распознан."""
    match = _COORD_RE.match(text.strip())
    if not match:
        return None
    g = match.groupdict()
    return (
        f"{g['lat_deg']}°{g['lat_min']}'{g['lat_sec']}\"{g['lat_dir'].upper()} "
        f"{g['lon_deg']}°{g['lon_min']}'{g['lon_sec']}\"{g['lon_dir'].upper()}"
    )


def coordinates_to_maps_url(text: str) -> str | None:
    """Строит ссылку на Google Maps по DMS-координатам. None, если формат не распознан."""
    match = _COORD_RE.match(text.strip())
    if not match:
        return None
    g = match.groupdict()

    def _to_decimal(deg, minutes, seconds, direction) -> float:
        value = float(deg) + float(minutes) / 60 + float(seconds) / 3600
        if direction.upper() in ("S", "W"):
            value = -value
        return value

    lat = _to_decimal(g["lat_deg"], g["lat_min"], g["lat_sec"], g["lat_dir"])
    lon = _to_decimal(g["lon_deg"], g["lon_min"], g["lon_sec"], g["lon_dir"])
    return f"https://www.google.com/maps?q={lat:.6f},{lon:.6f}"
