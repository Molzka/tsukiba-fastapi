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
cp .env.example .env
```

В Windows PowerShell используйте `Copy-Item .env.example .env`.
Заполните в `.env` два независимых секрета: `MANAGE_KEY` (ключ доступа к настройкам)
и `CAPTCHA_SECRET` (ключ подписи резервной капчи). Для генерации каждого значения:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Затем запустите:

```bash
docker compose up --build
```

После запуска откройте:

- доска: <http://localhost:8000/>
- управление: `http://localhost:8000/manage?key=<MANAGE_KEY из .env>`

Compose откажется запускаться с пустыми секретами. `.env` исключён из Git и Docker-образа.
Миграции применяются автоматически перед запуском сервера, в том числе к пустой базе.
SQLite хранится в именованном томе `board-data`; существующие данные при перезапуске сохраняются.
Адреса БД и Redis внутри Compose заданы для контейнеров; `DATABASE_URL` и `REDIS_URL`
из `.env.example` предназначены для локального запуска без Docker.

## Первый запуск

1. Откройте `/manage?key=<MANAGE_KEY из .env>`.
2. Укажите лимиты доски, тип капчи и пароль администратора.
3. Подтвердите пароль и сохраните настройки. Пароль обязателен, должен содержать
   от 1 до 100 символов и не может состоять только из пробелов.

Пока настройки не созданы, все страницы кроме `/manage` возвращают 404.

## Локальный запуск без Docker

Создайте и заполните `.env`, как описано выше. Приложение и Alembic читают один `DATABASE_URL`.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
alembic upgrade head
uvicorn app.main:app --reload
```

Для полноценной работы локально нужен Redis по адресу из `REDIS_URL`. Если Redis недоступен при старте, приложение использует резервную HMAC-проверку капчи, но в Docker Compose Redis включён по умолчанию.

Для видео установите `ffmpeg` и `ffprobe` и добавьте их в `PATH`. ExifTool используется
для удаления метаданных поддерживаемых форматов, если установлен; метаданные WebM
не изменяются. В Docker все три инструмента уже включены.

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
