"""scripts/reset_local_db.py — удаляет локальную бета-базу (beta.db) без
повторного подтягивания снимка прода (это, в отличие от простого удаления
файла, делает сам bot.py при каждом запуске — см. database/beta_sync.py).
Полезно, если нужно просто быстро всё стереть, не запуская бота следующим
шагом, или его совсем нет под рукой.

Запуск: python -m scripts.reset_local_db
"""
import config


def run() -> None:
    if not config.IS_BETA_MODE:
        raise SystemExit("Отказ: reset_local_db предназначен только для бета-бота (BETA_BOT_TOKEN).")

    if config.BETA_DB_PATH.exists():
        config.BETA_DB_PATH.unlink()
        print(f"[OK] удалён {config.BETA_DB_PATH}")
    else:
        print(f"[OK] {config.BETA_DB_PATH} не было — нечего удалять")


if __name__ == "__main__":
    run()
