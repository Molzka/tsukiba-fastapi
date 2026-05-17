from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_session
from app.deps import (
    api_error,
    error_response,
    get_redis,
    options_or_json_404,
    post_form_data,
    request_uploads,
)
from app.presentation import api_page_context
from app.services.board import (
    get_active_thread_posts,
    get_active_threads_list,
    get_options,
    get_post_info,
    sanitize_post,
    submit_post,
)
from app.services.captcha import issue_captcha, validate_captcha
from app.services.files import prepare_uploads
from app.templating import templates

router = APIRouter(prefix="/api")


@router.get("", response_class=HTMLResponse)
def api_page(request: Request, session: Session = Depends(get_session)):
    if not get_options(session):
        return error_response(request)
    return templates.TemplateResponse(request, "pages/api.html", api_page_context())


@router.get("/index")
def api_index(session: Session = Depends(get_session)):
    options_or_json_404(session)
    return get_active_threads_list(session)


@router.get("/thread/{thread_id:int}")
def api_thread(thread_id: int, session: Session = Depends(get_session)):
    options_or_json_404(session)
    posts = get_active_thread_posts(session, thread_id)
    if not posts or thread_id == 0:
        return api_error()
    return [sanitize_post(post) for post in posts]


@router.get("/id/{post_id:int}")
def api_post_info(post_id: int, session: Session = Depends(get_session)):
    options_or_json_404(session)
    post = get_post_info(session, post_id)
    if not post:
        return api_error()
    return sanitize_post(post, include_parent=True)


@router.get("/info")
def api_info(session: Session = Depends(get_session)):
    options = options_or_json_404(session)
    return {
        "max_file_size": options.max_file_size,
        "max_message_length": options.max_message_length,
    }


@router.get("/post")
async def api_captcha(request: Request, session: Session = Depends(get_session)):
    options = options_or_json_404(session)
    return await issue_captcha(get_redis(request), options)


@router.post("/post")
async def api_submit_post(request: Request, session: Session = Depends(get_session)):
    options = options_or_json_404(session)
    form = await post_form_data(request)
    if not form["captcha"] or not form["verify"]:
        return api_error("Необходимо решить капчу", 400)
    if not await validate_captcha(
        get_redis(request), options, form["captcha"], form["verify"]
    ):
        return api_error("Капча введена неверно", 400)
    uploads = await prepare_uploads(await request_uploads(request))
    result = submit_post(
        session,
        options,
        parent=form["parent"],
        message=form["message"],
        uploads=uploads,
        password=form["password"],
        sage=form["sage"],
        verify=form["verify"],
    )
    if isinstance(result, int):
        return {"post_id": result}
    return api_error(result, 400)
