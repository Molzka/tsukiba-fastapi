from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_session
from app.deps import error_response, get_redis, request_target
from app.presentation import (
    archive_context,
    archived_thread_context,
    catalog_context,
    index_context,
    info_context,
    short_context,
    thread_context,
)
from app.services.board import get_options
from app.services.captcha import issue_captcha
from app.templating import templates

router = APIRouter()


@router.get("/favicon.ico")
def favicon():
    favicon_path = Path("favicon.ico")
    if favicon_path.exists():
        return FileResponse(favicon_path)
    return HTMLResponse(status_code=404)


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, session: Session = Depends(get_session)):
    options = get_options(session)
    if not options:
        return error_response(request)
    captcha = await issue_captcha(get_redis(request), options)
    status, context = index_context(
        session, options, captcha, 0, request_target(request)
    )
    if status != 200:
        return error_response(request, status_code=status)
    return templates.TemplateResponse(request, "pages/index.html", context)


@router.get("/{page:int}", response_class=HTMLResponse)
async def index_page(
    page: int, request: Request, session: Session = Depends(get_session)
):
    options = get_options(session)
    if not options:
        return error_response(request)
    captcha = await issue_captcha(get_redis(request), options)
    status, context = index_context(
        session, options, captcha, page, request_target(request)
    )
    if status != 200:
        return error_response(request, status_code=status)
    return templates.TemplateResponse(request, "pages/index.html", context)


@router.get("/thread/{thread_id:int}", response_class=HTMLResponse)
async def thread_page(
    thread_id: int, request: Request, session: Session = Depends(get_session)
):
    options = get_options(session)
    if not options:
        return error_response(request)
    captcha = await issue_captcha(get_redis(request), options)
    status, context, redirect_to = thread_context(
        session, options, captcha, thread_id, request_target(request)
    )
    if redirect_to:
        return RedirectResponse(redirect_to, status_code=302)
    if status != 200:
        return error_response(request, status_code=status)
    return templates.TemplateResponse(request, "pages/thread.html", context)


@router.get("/short/{thread_id:int}", response_class=HTMLResponse)
async def short_page(
    thread_id: int, request: Request, session: Session = Depends(get_session)
):
    options = get_options(session)
    if not options:
        return error_response(request)
    captcha = await issue_captcha(get_redis(request), options)
    status, context, redirect_to = short_context(
        session, options, captcha, thread_id, request_target(request)
    )
    if redirect_to:
        return RedirectResponse(redirect_to, status_code=302)
    if status != 200:
        return error_response(request, status_code=status)
    return templates.TemplateResponse(request, "pages/thread.html", context)


@router.get("/catalog", response_class=HTMLResponse)
def catalog_page(
    request: Request, search: str = "", session: Session = Depends(get_session)
):
    if not get_options(session):
        return error_response(request)
    return templates.TemplateResponse(
        request, "pages/catalog.html", catalog_context(session, search)
    )


@router.get("/info", response_class=HTMLResponse)
def info_page(request: Request, session: Session = Depends(get_session)):
    options = get_options(session)
    if not options:
        return error_response(request)
    return templates.TemplateResponse(request, "pages/info.html", info_context(options))


@router.get("/archive", response_class=HTMLResponse)
def archive_page(request: Request, session: Session = Depends(get_session)):
    if not get_options(session):
        return error_response(request)
    status, context = archive_context(session, 0)
    if status != 200:
        return error_response(request, status_code=status)
    return templates.TemplateResponse(request, "pages/archive.html", context)


@router.get("/archive/{page:int}", response_class=HTMLResponse)
def archive_page_number(
    page: int, request: Request, session: Session = Depends(get_session)
):
    if not get_options(session):
        return error_response(request)
    status, context = archive_context(session, page)
    if status != 200:
        return error_response(request, status_code=status)
    return templates.TemplateResponse(request, "pages/archive.html", context)


@router.get("/archived/{thread_id:int}", response_class=HTMLResponse)
def archived_thread_page(
    thread_id: int, request: Request, session: Session = Depends(get_session)
):
    if not get_options(session):
        return error_response(request)
    status, context, redirect_to = archived_thread_context(session, thread_id)
    if redirect_to:
        return RedirectResponse(redirect_to, status_code=302)
    if status != 200:
        return error_response(request, status_code=status)
    return templates.TemplateResponse(request, "pages/archived_thread.html", context)
