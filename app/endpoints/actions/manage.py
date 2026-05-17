from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_session
from app.deps import error_response, parse_int
from app.security import verify_password
from app.services.board import (
    create_options,
    get_options,
    manage_thread_statuses,
    update_options,
)

router = APIRouter()


@router.post("/manage", response_class=HTMLResponse)
@router.post("/manage/{page:int}", response_class=HTMLResponse)
async def manage_submit(
    request: Request,
    page: int = 0,
    key: str | None = None,
    session: Session = Depends(get_session),
):
    if key != settings.manage_key:
        return error_response(request)
    form = await request.form()
    action = str(form.get("action") or "")
    captcha = str(form.get("captcha") or "")
    numeric_fields = [
        "max_file_size",
        "bump_limit",
        "max_threads",
        "max_message_length",
    ]
    if action not in {"initial_setup", "setup"} or not captcha:
        return error_response(request, "Не все поля заполнены", 400)
    values = {field: parse_int(form.get(field), -1) for field in numeric_fields}
    if any(value < 0 for value in values.values()):
        return error_response(request, "Не все поля заполнены", 400)
    stop_board = bool(parse_int(form.get("stop_board"), 0))
    options = get_options(session)
    if action == "initial_setup":
        if options:
            return RedirectResponse(
                f"/manage?key={settings.manage_key}", status_code=303
            )
        password = str(form.get("password") or "")
        confirm = str(form.get("confirm_password") or "")
        if password != confirm:
            return error_response(request, "Пароль не совпадает", 400)
        create_options(
            session,
            max_file_size_mb=values["max_file_size"],
            bump_limit=values["bump_limit"],
            max_threads=values["max_threads"],
            max_message_length=values["max_message_length"],
            captcha=captcha,
            stop_board=stop_board,
            password=password,
            post_id_seed=parse_int(form.get("id"), 0),
        )
        return RedirectResponse(f"/manage?key={settings.manage_key}", status_code=303)

    if not options:
        return error_response(request)
    password = str(form.get("password") or "")
    if not verify_password(password, options.password_hash):
        return error_response(request, "Пароль введён неверно", 400)
    new_password = str(form.get("new_password") or "")
    confirm_new_password = str(form.get("confirm_new_password") or "")
    if new_password != confirm_new_password:
        return error_response(request, "Новый пароль не совпадает", 400)
    update_options(
        session,
        options,
        max_file_size_mb=values["max_file_size"],
        bump_limit=values["bump_limit"],
        max_threads=values["max_threads"],
        max_message_length=values["max_message_length"],
        captcha=captcha,
        stop_board=stop_board,
        new_password=new_password or None,
    )
    manage_thread_statuses(session, options)
    return RedirectResponse(f"/manage?key={settings.manage_key}", status_code=303)
