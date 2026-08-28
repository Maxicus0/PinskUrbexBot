# PinskUrbexBot

Telegram-бот — архив заброшенных объектов города, работающий на
**кредитах доверия**: пользователи присылают инсайды (новый объект,
залаз, координаты, новости), админы оценивают их числом, за это
начисляются кредиты, которые открывают доступ к карточкам объектов.

Стек: Python, aiogram 3, PostgreSQL.

## Быстрый старт

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# впишите в .env: BOT_TOKEN (от @BotFather), ADMIN_IDS (ваш telegram id),
# DATABASE_URL (строка подключения к PostgreSQL)

python bot.py
```

Схема БД создаётся автоматически при первом запуске (`database/schema.sql`).

### Бета-бот для локального теста (опционально)

`BETA_BOT_TOKEN` — токен **второго** бота (от @BotFather) для локальных
запусков (например, из PyCharm), чтобы проверять новые функции на **той же**
БД, не трогая продакшн. С боевым ботом он никогда не запускается параллельно
— активен всегда только один:

- `BOT_TOKEN` заполнен → используется он (боевой), `BETA_BOT_TOKEN`
  игнорируется, даже если тоже прописан в `.env`;
- `BOT_TOKEN` пуст → используется `BETA_BOT_TOKEN` (локальный бета-режим).

`DATABASE_URL` в обоих случаях общий — те же пользователи, кредиты, объекты
архива и инсайды, что и у боевого бота.

⚠️ `file_id` фотографии привязан к боту, который её принял, — через другой
бот её не переслать (Telegram ответит `Wrong file identifier`). Объекты с
реальными фото добавляйте через боевой бот; если фото всё же добавлено через
бета-бот, карточка не упадёт — просто покажется без фото.

Проверить слой БД и утилиты без Telegram:
```bash
python -m scripts.smoke_test
```

## Структура

```
bot.py                 Точка входа
config.py              Конфигурация из .env
database/              Подключение к PostgreSQL, схема, репозитории
handlers/               Обработчики сообщений и колбэков
keyboards/              Клавиатуры
states/                 FSM-состояния
utils/                  Форматирование, доступ, уровни, валидация координат,
                        доставка сообщений при двух ботах (bot_delivery.py)
scripts/smoke_test.py   Самопроверка БД без Telegram
```

Вся работа с БД — только через `database/*_repo.py`. Любой пользовательский
текст в сообщениях бота проходит через `utils.formatting.esc()` (бот
работает с `ParseMode.HTML`).

## Деплой на Render

Конфигурация — в `render.yaml` (Blueprint): Web Service + managed
PostgreSQL, оба на бесплатном тарифе. Бот работает через long polling, а
не через HTTP, но у Render бесплатный план есть только у Web Service —
поэтому `bot.py` дополнительно поднимает лёгкую HTTP-заглушку на `$PORT`
(`GET /health` → `200 OK`) только для healthcheck'а самого Render.

### Пуш на GitHub

```bash
git init -b main            # если репозиторий ещё не инициализирован
git add .
git commit -m "Release 0.1"
git remote add origin git@github.com:<ваш-аккаунт>/PinskUrbexBot.git
git push -u origin main
```

`.env` в коммит не попадёт — он в `.gitignore`.

### Деплой

1. В [Render Dashboard](https://dashboard.render.com) → **New** → **Blueprint** → выберите репозиторий на GitHub.
2. Render прочитает `render.yaml`, попросит `BOT_TOKEN` (от @BotFather) и `ADMIN_IDS` — впишите вручную, в репозитории их нет.
3. `DATABASE_URL` подставится сама из связанной free-базы.

Оговорки бесплатного тарифа:
- **Web Service засыпает** после ~15 минут без HTTP-запросов и просыпается ~30-60 сек по следующему. Сам бот HTTP-трафик не получает, поэтому для действительно круглосуточной работы нужен внешний пингер — например, бесплатный [UptimeRobot](https://uptimerobot.com), раз в 10 минут дергающий `https://<ваш-сервис>.onrender.com/health`.
- **Free PostgreSQL живёт 30 дней**, потом Render её удаляет. Для боевой эксплуатации нужно поменять `plan: free` на `basic-256mb` (или выше) у базы в `render.yaml`.
