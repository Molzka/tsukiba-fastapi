from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_session
from app.deps import error_response, parse_int
from app.services.board import board_is_setup, moderate_posts, restore_posts

router = APIRouter()


@router.post("/mod", response_class=HTMLResponse)
async def mod_submit(request: Request, session: Session = Depends(get_session)):
    if not board_is_setup(session):
        return error_response(request)
    form = await request.form()
    post_ids = [parse_int(value) for value in form.getlist("mod-box")]
    password = str(form.get("mod-pass") or "")
    return_url = str(form.get("return-url") or "/")
    if not post_ids:
        return error_response(request, "Вы ничего не выбрали", 400)
    if not password:
        return error_response(request, "Вы не ввели пароль", 400)
    if len(password) > 100:
        return error_response(request, "Пароль не должен превышать 100 символов", 400)
    if moderate_posts(session, post_ids, password):
        return RedirectResponse(return_url, status_code=303)
    return error_response(request, "Неверный пароль", 400)


@router.post("/modlog", response_class=HTMLResponse)
@router.post("/modlog/{page:int}", response_class=HTMLResponse)
async def restore_from_modlog(
    request: Request, page: int = 0, session: Session = Depends(get_session)
):
    form = await request.form()
    post_ids = [parse_int(value) for value in form.getlist("mod-box")]
    password = str(form.get("mod-pass") or "")
    if not post_ids:
        return error_response(request, "Вы ничего не выбрали", 400)
    if not password:
        return error_response(request, "Вы не ввели пароль", 400)
    restored = restore_posts(session, post_ids, password)
    if restored:
        return RedirectResponse("/modlog", status_code=303)
    return error_response(
        request, "Неверный пароль или нет постов для восстановления", 400
    )
