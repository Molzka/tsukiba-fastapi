from typing import Any
from contextlib import asynccontextmanager

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy.orm import Session
from starlette.datastructures import FormData, UploadFile
from starlette.formparsers import FormParser, MultiPartException, MultiPartParser

from app.models import BoardOption
from app.services.board import get_options
from app.services.files import MAX_FILES, SIZE_ERROR, UploadError
from app.templating import templates


def get_redis(request: Request) -> Redis | None:
    return getattr(request.app.state, "redis", None)


def request_target(request: Request) -> str:
    query = f"?{request.url.query}" if request.url.query else ""
    return f"{request.url.path}{query}"


def error_response(
    request: Request, message: str = "Страница не найдена", status_code: int = 404
):
    return templates.TemplateResponse(
        request,
        "pages/error.html",
        {"title": "Ошибка", "message": message},
        status_code=status_code,
    )


def api_error(
    message: str = "Страница не найдена", status_code: int = 404
) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status_code)


def options_or_json_404(session: Session) -> BoardOption:
    options = get_options(session)
    if not options:
        raise HTTPException(status_code=404, detail="Страница не найдена")
    return options


class BodyLimitExceeded(MultiPartException):
    pass


@asynccontextmanager
async def read_post_form(request: Request, options: BoardOption):
    multipart = (
        request.headers.get("content-type", "").split(";", 1)[0].lower()
        == "multipart/form-data"
    )
    limit = options.max_message_length * 12 + 64 * 1024
    if multipart:
        limit += options.max_file_size
    received = 0

    async def limited_stream():
        nonlocal received
        async for chunk in request.stream():
            received += len(chunk)
            if received > limit:
                raise BodyLimitExceeded(SIZE_ERROR)
            yield chunk

    try:
        if multipart:
            parser = MultiPartParser(
                request.headers,
                limited_stream(),
                max_files=MAX_FILES,
                max_fields=16,
                max_part_size=max(4096, options.max_message_length * 4),
            )
        else:
            parser = FormParser(request.headers, limited_stream())
        form = await parser.parse()
    except BodyLimitExceeded as exc:
        raise UploadError(SIZE_ERROR, 413) from exc
    except MultiPartException as exc:
        message = (
            "Разрешено прикрепление не более 4 файлов"
            if "Too many files" in str(exc)
            else "Не удалось прочитать форму. Проверьте поля и прикреплённые файлы"
        )
        raise UploadError(message) from exc
    try:
        yield form
    finally:
        await form.close()


def request_uploads(form: FormData) -> list[UploadFile]:
    uploads: list[UploadFile] = []
    for key in ("files[]", "files"):
        for value in form.getlist(key):
            if isinstance(value, UploadFile):
                uploads.append(value)
    return uploads


def post_form_data(form: FormData) -> dict[str, Any]:
    return {
        "parent": parse_int(form.get("parent")),
        "message": str(form.get("message") or ""),
        "captcha": str(form.get("captcha") or ""),
        "verify": str(form.get("verify") or ""),
        "password": str(form.get("password") or "") or None,
        "sage": form.get("sage") is not None,
        "page_type": str(form.get("page-type") or "normal"),
    }


def parse_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
