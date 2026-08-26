"""config.py — загрузка конфигурации бота из .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN не найден. Скопируйте .env.example в .env и укажите токен бота."
    )

DATABASE_URL: str = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL не найден. Укажите строку подключения к PostgreSQL в .env."
    )


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

CITY_NAME: str = os.getenv("CITY_NAME", "N")

# Порт для HTTP-заглушки (нужен только на Render: Web Service обязан
# слушать порт, иначе деплой считается упавшим). Render сам подставляет
# PORT через переменную окружения — локально не используется.
PORT: int = int(os.getenv("PORT", "10000"))

MIN_INSIGHT_CREDITS = 0
MAX_INSIGHT_CREDITS = 10

# Уровни доверия — косметическая надстройка над credits (см. utils/levels.py).
# (порог кредитов, название уровня, цвет-эмодзи), по возрастанию порога.
LEVELS: list[tuple[int, str, str]] = [
    (0, "Кукла", "⚪"),
    (10, "Баянщик", "🔵"),
    (50, "Нормис", "🟡"),
    (100, "Сталкер", "🔴"),
    (250, "Истинный урбанекс", "🟣"),
]
