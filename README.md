# Цукиба

Анонимная имиджборда тсукиба, переписанная на FastAPI.

Стек:

- FastAPI
- Jinja2 HTML-шаблоны
- SQLAlchemy
- Alembic
- Redis
- Docker и Docker Compose
- Argon2 для хеширования паролей
- Pillow, FFmpeg и ExifTool для обработки медиа

## Запуск через Docker Compose

```bash
docker compose up --build
```

После запуска откройте:

- доска: <http://localhost:8000/>
- управление: <http://localhost:8000/manage?key=secretkey>

В production обязательно замените переменные `MANAGE_KEY` и `CAPTCHA_SECRET` в `docker-compose.yml`.

## Первый запуск

1. Откройте `/manage?key=secretkey`.
2. Укажите лимиты доски, тип капчи и пароль администратора.
3. Сохраните настройки.

Пока настройки не созданы, все страницы кроме `/manage` возвращают 404.

## Локальный запуск без Docker

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
alembic upgrade head
uvicorn app.main:app --reload
```

Для полноценной работы локально нужен Redis по адресу из `REDIS_URL`. Если Redis недоступен, приложение использует резервную HMAC-проверку капчи, но в Docker Compose Redis включён по умолчанию.

## API

- `GET /api/index` — список активных тредов
- `GET /api/thread/{id}` — содержимое треда
- `GET /api/id/{id}` — пост по номеру
- `GET /api/info` — лимиты доски
- `GET /api/post` — капча для постинга
- `POST /api/post` — создание треда или ответа

Для `POST /api/post` передаются `parent`, `message`, `captcha`, `verify`, опционально `sage`, `password` и файлы `files` или `files[]`.

## Структура

- `app/endpoints/pages/` — HTML-страницы
- `app/endpoints/api/` — JSON API
- `app/endpoints/actions/` — POST-действия форм
- `app/templates/pages/` — шаблоны страниц
- `app/templates/partials/` — общие фрагменты HTML
- `app/services/` — бизнес-логика доски, файлов, капчи и текста
