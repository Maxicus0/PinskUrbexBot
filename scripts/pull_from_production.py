"""scripts/pull_from_production.py — вручную пересоздать beta.db из снимка
прода. То же самое автоматически делает bot.py при каждом запуске
бета-бота (см. database/beta_sync.py) — этот скрипт полезен, если нужно
обновить локальный снимок без перезапуска самого бота.

Запуск: python -m scripts.pull_from_production
"""
from database.beta_sync import rebuild_from_production

if __name__ == "__main__":
    rebuild_from_production()
