"""scripts/generate_secret_key.py — генерирует случайный APP_SECRET_KEY.

Ключ шифрования персональных данных (см. utils/crypto.py) должен быть
настоящей случайностью, а не придуманной человеком фразой/паролем — этот
скрипт просто печатает 32 случайных байта в base64, готовые вставить в
.env как APP_SECRET_KEY.

На Render этот шаг обычно не нужен вовсе — render.yaml уже настроен на
generateValue: true, платформа сгенерирует ключ сама при деплое. Скрипт
пригождается для локального запуска/тестов или другого хостинга.

Запуск: python -m scripts.generate_secret_key
"""
import base64
import secrets


def run() -> None:
    key = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
    print(key)
    print()
    print("Добавьте в .env строку:")
    print(f"APP_SECRET_KEY={key}")
    print()
    print(
        "Храните этот ключ отдельно от базы данных и от репозитория (он и так "
        "в .gitignore через .env). Потеря ключа делает все зашифрованные "
        "telegram_id/username/full_name/заметки в БД навсегда нечитаемыми — "
        "сделайте резервную копию ключа в надёжном месте (менеджер паролей и т.п.)."
    )


if __name__ == "__main__":
    run()
