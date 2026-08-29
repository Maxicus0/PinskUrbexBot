"""config.py — загрузка конфигурации бота из .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()

# BETA_BOT_TOKEN — токен второго бота, только для локальных запусков (например,
# из PyCharm), никогда не работает параллельно с боевым. Активен всегда ровно
# один бот: если BOT_TOKEN заполнен — используется он, а BETA_BOT_TOKEN
# игнорируется (даже если тоже задан — это защищает от случайного запуска двух
# ботов на сервере); если BOT_TOKEN пуст — используется BETA_BOT_TOKEN. Оба
# режима работают на одной DATABASE_URL, так что пользователи/кредиты/объекты/
# инсайды общие. file_id фотографий привязан к принявшему их боту, поэтому
# объекты с реальными фото добавляйте через боевой бот.
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

CITY_NAME: str = os.getenv("CITY_NAME", "N")

# Порт для HTTP-заглушки (нужен только на Render: Web Service обязан
# слушать порт, иначе деплой считается упавшим). Render сам подставляет
# PORT через переменную окружения — локально не используется.
PORT: int = int(os.getenv("PORT", "10000"))

MIN_INSIGHT_CREDITS = 0
MAX_INSIGHT_CREDITS = 10

# Максимум медиафайлов (фото + видео суммарно) на один инсайд. Лимит не
# анонсируется в тексте сценария (handlers/insight_submit.py) — пользователь
# просто узнаёт о нём, если попробует прикрепить больше.
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
