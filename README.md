# Calorie Compass

Многопользовательский веб-сервис для учета калорий и КБЖУ.

## Что умеет

- отдельные страницы входа и регистрации;
- общий справочник блюд и продуктов для всех пользователей;
- поле изготовителя у каждой позиции справочника;
- личный дневник питания и персональные цели по КБЖУ;
- дневной прогресс и аналитику выполнения нормы.

## Основные файлы

- `server.py` - backend на стандартной библиотеке Python;
- `index.html`, `app.js` - основное приложение;
- `login.html`, `login.js` - вход;
- `register.html`, `register.js` - регистрация;
- `requirements.txt` - Python-зависимости для PostgreSQL;
- `Dockerfile` - контейнерный запуск;
- `render.yaml` - готовая конфигурация для Render.

## Локальный запуск

```bash
cd "/Users/semensharonov/Documents/New project"
python3 server.py
```

Адреса:

- `http://127.0.0.1:4173/login` - вход
- `http://127.0.0.1:4173/register` - регистрация
- `http://127.0.0.1:4173/` - приложение

## Docker

Сборка:

```bash
docker build -t calorie-compass .
```

Запуск:

```bash
docker run -p 4173:4173 -v "$(pwd)/data:/data" -e COOKIE_SECURE=false calorie-compass
```

## Деплой на Render

В проект уже добавлен `render.yaml`, так что сервис можно публиковать как Blueprint.

1. Загрузите проект в GitHub.
2. В Render выберите `New +` -> `Blueprint`.
3. Подключите репозиторий.
4. Render сам подхватит `render.yaml`, создаст web service и PostgreSQL database.
5. После деплоя получите единый публичный URL для всех пользователей.

Для Render уже настроено:

- health check: `/healthz`
- managed PostgreSQL через `DATABASE_URL`
- secure cookie в production

## Переменные окружения

- `HOST` - хост для сервера, по умолчанию `0.0.0.0`
- `PORT` - порт, по умолчанию `4173`
- `DATA_DIR` - директория для SQLite-файла
- `DB_PATH` - явный путь до SQLite, если нужен
- `DATABASE_URL` - если задан, приложение использует PostgreSQL вместо SQLite
- `COOKIE_SECURE` - ставить ли флаг `Secure` у cookie

## Данные

- локальная тестовая база не должна попадать в репозиторий;
- в production на Render данные хранятся в PostgreSQL;
- справочник блюд общий для всех пользователей, а записи и цели персональные.
