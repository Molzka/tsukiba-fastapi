from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from app.models import BoardOption
from app.services.board import get_options
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


async def request_uploads(request: Request) -> list[UploadFile]:
    form = await request.form()
    uploads: list[UploadFile] = []
    for key in ("files[]", "files"):
        for value in form.getlist(key):
            if isinstance(value, UploadFile):
                uploads.append(value)
    return uploads


async def post_form_data(request: Request) -> dict[str, Any]:
    form = await request.form()
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
