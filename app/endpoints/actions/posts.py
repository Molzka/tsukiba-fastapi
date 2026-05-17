from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_session
from app.deps import error_response, get_redis, post_form_data, request_uploads
from app.services.board import get_options, submit_post
from app.services.captcha import validate_captcha
from app.services.files import prepare_uploads

router = APIRouter()


@router.post("/post", response_class=HTMLResponse)
async def post_submit(request: Request, session: Session = Depends(get_session)):
    options = get_options(session)
    if not options:
        return error_response(request)
    form = await post_form_data(request)
    if not form["captcha"] or not form["verify"]:
        return error_response(request, "Необходимо решить капчу", 400)
    if not await validate_captcha(
        get_redis(request), options, form["captcha"], form["verify"]
    ):
        return error_response(request, "Капча введена неверно", 400)
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
        thread_id = form["parent"] or result
        path = (
            f"/short/{thread_id}"
            if form["page_type"] == "short"
            else f"/thread/{thread_id}"
        )
        return RedirectResponse(f"{path}#{result}", status_code=303)
    return error_response(request, result, 400)
