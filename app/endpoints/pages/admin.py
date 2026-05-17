from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_session
from app.deps import error_response, request_target
from app.presentation import manage_context, modlog_context
from app.services.board import get_options
from app.templating import templates

router = APIRouter()


@router.get("/modlog", response_class=HTMLResponse)
def modlog_page(request: Request, session: Session = Depends(get_session)):
    if not get_options(session):
        return error_response(request)
    status, context = modlog_context(session, 0)
    if status != 200:
        return error_response(request, status_code=status)
    return templates.TemplateResponse(request, "pages/modlog.html", context)


@router.get("/modlog/{page:int}", response_class=HTMLResponse)
def modlog_page_number(
    page: int, request: Request, session: Session = Depends(get_session)
):
    if not get_options(session):
        return error_response(request)
    status, context = modlog_context(session, page)
    if status != 200:
        return error_response(request, status_code=status)
    return templates.TemplateResponse(request, "pages/modlog.html", context)


@router.get("/manage", response_class=HTMLResponse)
@router.get("/manage/{page:int}", response_class=HTMLResponse)
def manage_page(
    request: Request,
    page: int = 0,
    key: str | None = None,
    session: Session = Depends(get_session),
):
    if key != settings.manage_key:
        return error_response(request)
    status, context = manage_context(
        session,
        get_options(session),
        page,
        settings.manage_key,
        request_target(request),
    )
    if status != 200:
        return error_response(request, status_code=status)
    return templates.TemplateResponse(request, "pages/manage.html", context)
