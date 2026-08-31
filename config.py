"""config.py — загрузка конфигурации бота из .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()

# BETA_BOT_TOKEN — токен второго бота, только для локальных запусков.
# Активен всегда ровно один бот: BOT_TOKEN заполнен → боевой режим,
# бот работает напрямую с PostgreSQL (DATABASE_URL). Иначе, если заполнен
# BETA_BOT_TOKEN → бета-режим: при каждом запуске локальная SQLite
# (BETA_DB_PATH ниже) стирается и пересоздаётся заново из свежего снимка
# той же PostgreSQL (см. database/beta_sync.py) — сам бета-бот дальше
# работает только с этой локальной копией, боевую базу не трогает.
BETA_BOT_TOKEN: str = os.getenv("BETA_BOT_TOKEN", "").strip()

if BOT_TOKEN:
    ACTIVE_BOT_TOKEN: str = BOT_TOKEN
    IS_BETA_MODE: bool = False
elif BETA_BOT_TOKEN:
    ACTIVE_BOT_TOKEN = BETA_BOT_TOKEN
    IS_BETA_MODE = True
else:
    raise RuntimeError(
        "Не найден ни BOT_TOKEN, ни BETA_BOT_TOKEN. Укажите хотя бы один в .env."
    )

# Нужен в обоих режимах: в боевом — как основная база бота, в бета — как
# источник, из которого при каждом локальном запуске подтягивается снимок
# в локальную SQLite (см. BETA_DB_PATH и database/beta_sync.py).
DATABASE_URL: str = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL не найден. Укажите строку подключения к PostgreSQL в .env "
        "— она нужна и боевому боту (как основная база), и бета-боту (как "
        "источник снимка для локальной SQLite)."
    )

if IS_BETA_MODE:
    # Пересоздаётся заново при каждом запуске (database/beta_sync.py) — не
    # надо ни бэкапить, ни переживать за содержимое.
    BETA_DB_PATH: Path = BASE_DIR / "beta.db"


def _parse_admin_ids(raw: str) -> set[int]:
    ids: set[int] = set()
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if chunk:
            ids.add(int(chunk))
    return ids


ADMIN_IDS: set[int] = _parse_admin_ids(os.getenv("ADMIN_IDS", ""))

# Раздел "Архив" открыт всем без порога — скрыты (по кредитам доверия)
# только отдельные объекты внутри него, у каждого свой min_credits.
MIN_OBJECT_CREDITS = 0
MAX_OBJECT_CREDITS = 100

# Уровни опасности объекта — обязательный атрибут каждого объекта архива
# (config.DANGER_LEVELS: код, подпись, эмодзи), по возрастанию серьёзности.
# 'black' формально идёт последним по просьбе постановки, но по смыслу это
# не "опаснее красного", а отдельный статус "мало данных для оценки".
DANGER_LEVELS: list[tuple[str, str, str]] = [
    ("white", "Абсолютно безопасно", "⚪"),
    ("green", "Тихо зашли и гуляйте", "🟢"),
    ("yellow", "Успей отфоткать хабар и уйти", "🟡"),
    ("red", "Огромный шанс запала", "🔴"),
    ("black", "Недостаточно инфы", "⚫"),
]
DEFAULT_DANGER_LEVEL = "black"  # дефолт для старых объектов при миграции — честно отражает "не оценивали"

# Режимы отображения объектов в списке "🗂 Архив" (см. /settings,
# handlers/settings.py, utils.formatting.format_object_teaser) — личная
# настройка пользователя (users.archive_display_mode), не влияет на других.
ARCHIVE_DISPLAY_MODES: list[tuple[str, str]] = [
    ("standard", "🗂 Стандартный (без цвета опасности)"),
    ("danger_color", "🎨 Цвет опасности вместо иконки"),
]
DEFAULT_ARCHIVE_DISPLAY_MODE = "standard"

CITY_NAME: str = os.getenv("CITY_NAME", "N")

# Ссылка на GitHub-репозиторий проекта — используется командой /about.
# Необязательная: если не заполнена, /about не падает, просто отвечает,
# что автор, похоже, обнаглел и закрыл исходники (см. handlers/common.py).
GITHUB_REPO_URL: str = os.getenv("GITHUB_REPO_URL", "").strip()

# Порт для HTTP-заглушки (нужен только на Render: Web Service обязан
# слушать порт, иначе деплой считается упавшим). Локально не используется.
PORT: int = int(os.getenv("PORT", "10000"))

MIN_INSIGHT_CREDITS = 0
MAX_INSIGHT_CREDITS = 10

# Максимум медиафайлов (фото + видео суммарно) на один инсайд.
MAX_INSIGHT_MEDIA = 5

# Уровни доверия — косметическая надстройка над credits (см. utils/levels.py).
# (порог кредитов, название уровня, цвет-эмодзи), по возрастанию порога.
LEVELS: list[tuple[int, str, str]] = [
    (0, "Кукла", "⚪"),
    (10, "Баянщик", "🔵"),
    (30, "Нормис", "🟢"),
    (60, "Опытный", "🟠"),
    (100, "Сталкер", "🔴"),
    (250, "Истинный урбекс", "⚫"),
]
