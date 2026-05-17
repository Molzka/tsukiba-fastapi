import html
import math
import re
from pathlib import Path
from typing import Any

from PIL import Image
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import BoardOption, Post
from app.services.board import (
    STATUS_ACTIVE,
    STATUS_ADMIN_DELETED,
    STATUS_ARCHIVED,
    STATUS_OP_DELETED,
    count_replies,
    get_replies_to_post,
    get_threads,
    post_stats,
    search_in_thread,
)
from app.services.files import get_subdir_path
from app.services.text import readable_bytes, strip_tags, truncate_string


def pagination_items(
    current: int, total: int, first_path: str, path_prefix: str, query: str = ""
) -> list[dict[str, Any]]:
    items = []
    for page in range(total):
        if page == current:
            items.append({"label": str(page), "url": None, "current": True})
        elif page == 0:
            items.append(
                {"label": "0", "url": f"{first_path}{query}", "current": False}
            )
        else:
            items.append(
                {
                    "label": str(page),
                    "url": f"{path_prefix}/{page}{query}",
                    "current": False,
                }
            )
    return items


def file_parts(post: Post) -> list[tuple[str, str]]:
    files = []
    for index in range(1, 5):
        filename = getattr(post, f"file{index}")
        info = getattr(post, f"file{index}_info")
        if filename:
            files.append((filename, info or ""))
    return files


def file_view(filename: str, file_info: str) -> dict[str, Any]:
    extension = Path(filename).suffix.lower().lstrip(".")
    file_hash = Path(filename).stem
    subdir = get_subdir_path(file_hash)
    thumb_name = f"{file_hash}.webp"
    thumb_path = settings.thumb_dir / subdir / thumb_name
    media_path = settings.media_dir / subdir / filename
    width = height = 0
    if thumb_path.exists():
        try:
            with Image.open(thumb_path) as image:
                width, height = image.size
        except OSError:
            pass
    return {
        "extension": extension.upper(),
        "info": file_info,
        "exists": media_path.exists(),
        "media_url": f"/media/{subdir}/{filename}",
        "thumb_url": f"/thumb/{subdir}/{thumb_name}",
        "width": width,
        "height": height,
        "is_video": extension in {"mp4", "webm"},
    }


def generate_post_links(session: Session, message: str | None) -> str:
    def replace(match: re.Match[str]) -> str:
        post_id = int(match.group(1))
        post = session.get(Post, post_id)
        if not post:
            return match.group(0)
        if post.status in {STATUS_ADMIN_DELETED, STATUS_OP_DELETED}:
            return f'<post-link class="deleted-reply" title="Пост удалён">&gt;&gt;{post_id}</post-link>'
        link_class = "thread-reply" if post.parent == 0 else "post-reply"
        files = file_parts(post)
        file_info = (
            "(Файл)&#013;"
            if len(files) == 1
            else ("(Файлы)&#013;" if len(files) > 1 else "")
        )
        snippet = truncate_string(
            strip_tags(file_info + (post.message or "").replace("<br>", "&#013;")), 500
        )
        thread_id = post.id if post.parent == 0 else post.parent
        prefix = "archived" if post.status == STATUS_ARCHIVED else "thread"
        return f'<a class="{link_class}" href="/{prefix}/{thread_id}#{post_id}" title="{html.escape(snippet)}"><post-link>&gt;&gt;{post_id}</post-link></a>'

    return re.sub(r"<post-link>&gt;&gt;(\d+)</post-link>", replace, message or "")


def backlinks_html(session: Session, post: Post, thread_id: int) -> str:
    replies = get_replies_to_post(session, post.id, thread_id)
    if not replies:
        return ""
    links = ", ".join(f"<post-link>&gt;&gt;{reply.id}</post-link>" for reply in replies)
    return generate_post_links(session, links)


def post_view(
    session: Session,
    post: Post,
    *,
    is_thread_page: bool = False,
    status: int = STATUS_ACTIVE,
) -> dict[str, Any]:
    is_thread = post.parent == 0
    files = [file_view(filename, info) for filename, info in file_parts(post)]
    file_class = (
        " post-with-file"
        if len(files) == 1
        else (" post-with-files" if len(files) > 1 else "")
    )
    thread_id = post.id if is_thread else post.parent

    show_mod_box = status != STATUS_ARCHIVED
    header_class = "empty-link"
    header_href = None
    action_html = ""
    if is_thread:
        if status == STATUS_ACTIVE:
            header_class = "header-link"
            header_href = f"/thread/{post.id}#{post.id}"
            action_html = (
                f' | <a class="reply-link" href="/thread/{post.id}#postform" title="Ответить">&gt;&gt;<span class="hidden">{post.id}</span></a>'
                if is_thread_page
                else f' | <a href="/thread/{post.id}">Открыть</a>'
            )
            if count_replies(session, post.id) >= 100 and not is_thread_page:
                action_html += f' | <a href="/short/{post.id}">Сокращённый</a>'
        elif status == STATUS_OP_DELETED:
            header_class = "header-link"
            header_href = f"/short/{post.id}#{post.id}"
            action_html = f' | <a class="reply-link" href="/short/{post.id}#postform" title="Ответить">&gt;&gt;<span class="hidden">{post.id}</span></a>'
        elif status == STATUS_ARCHIVED:
            header_class = "header-link"
            header_href = f"/archived/{post.id}#{post.id}"
            show_mod_box = False
    else:
        if status == STATUS_ACTIVE:
            header_class = "header-link"
            header_href = f"/thread/{post.parent}#{post.id}"
            if is_thread_page:
                action_html = f' | <a class="reply-link" href="/thread/{post.parent}#postform" title="Ответить">&gt;&gt;<span class="hidden">{post.id}</span></a>'
        elif status == STATUS_OP_DELETED:
            header_class = "header-link"
            header_href = f"/short/{post.parent}#{post.id}"
            action_html = f' | <a class="reply-link" href="/short/{post.parent}#postform" title="Ответить">&gt;&gt;<span class="hidden">{post.id}</span></a>'
        elif status == STATUS_ARCHIVED:
            header_class = "header-link"
            header_href = f"/archived/{post.parent}#{post.id}"
            show_mod_box = False

    return {
        "id": post.id,
        "parent": post.parent,
        "is_thread": is_thread,
        "anchor_class": "thread-id" if is_thread else "post-id",
        "post_class": "thread" if is_thread else "post",
        "file_class": file_class,
        "show_mod_box": show_mod_box,
        "header_class": header_class,
        "header_href": header_href,
        "time": post.time,
        "op_mod": bool(is_thread and post.password_hash),
        "sage": bool(not is_thread and post.sage),
        "action_html": action_html,
        "message_html": generate_post_links(session, post.message),
        "backlinks_html": backlinks_html(session, post, thread_id),
        "files": files,
    }


def thread_container_view(
    session: Session, thread: Post, *, preview_replies: bool = False
) -> dict[str, Any]:
    replies = []
    omitted = 0
    if preview_replies:
        replies = list(
            reversed(
                session.scalars(
                    select(Post)
                    .where(Post.parent == thread.id, Post.status == STATUS_ACTIVE)
                    .order_by(desc(Post.id))
                    .limit(3)
                ).all()
            )
        )
        omitted = count_replies(session, thread.id) - len(replies)
    return {
        "thread": post_view(session, thread),
        "replies": [post_view(session, reply) for reply in replies],
        "omitted": omitted,
    }


def catalog_thread_view(
    session: Session, thread: Post, *, archived: bool = False, tabindex: int = 0
) -> dict[str, Any] | None:
    files = file_parts(thread)
    if not files:
        return None
    filename = files[0][0]
    file_hash = Path(filename).stem
    subdir = get_subdir_path(file_hash)
    extension = Path(filename).suffix.lower().lstrip(".")
    return {
        "id": thread.id,
        "tabindex": tabindex,
        "href": f"/archived/{thread.id}" if archived else f"/thread/{thread.id}",
        "thumb_url": f"/thumb/{subdir}/{file_hash}.webp",
        "is_video": extension in {"mp4", "webm"},
        "reply_count": count_replies(session, thread.id),
        "op_mod": bool(thread.password_hash),
        "message_html": generate_post_links(session, thread.message),
    }


def index_context(
    session: Session,
    options: BoardOption,
    captcha: dict[str, str],
    page: int,
    request_url: str,
) -> tuple[int, dict[str, Any]]:
    page = max(0, page)
    threads_per_page = 20
    total_threads = len(get_threads(session))
    total_pages = max(1, math.ceil(total_threads / threads_per_page))
    if page >= total_pages:
        return 404, {}
    archive_count = (
        session.scalar(
            select(func.count())
            .select_from(Post)
            .where(Post.parent == 0, Post.status == STATUS_ARCHIVED)
        )
        or 0
    )
    threads = get_threads(
        session, limit=threads_per_page, offset=page * threads_per_page
    )
    return 200, {
        "title": "Главная",
        "options": options,
        "captcha": captcha,
        "pagination": pagination_items(page, total_pages, "/", ""),
        "has_archive": archive_count > 0,
        "return_url": request_url,
        "threads": [
            thread_container_view(session, thread, preview_replies=True)
            for thread in threads
        ],
    }


def thread_context(
    session: Session,
    options: BoardOption,
    captcha: dict[str, str],
    thread_id: int,
    request_url: str,
) -> tuple[int, dict[str, Any], str | None]:
    posts = list(
        session.scalars(
            select(Post)
            .where(
                (Post.id == thread_id) | (Post.parent == thread_id),
                Post.status.in_([STATUS_ACTIVE, STATUS_ARCHIVED]),
            )
            .order_by(Post.id)
        ).all()
    )
    if not posts or posts[0].parent != 0:
        return 404, {}, None
    if posts[0].status == STATUS_ARCHIVED:
        return 302, {}, f"/archived/{thread_id}"
    thread = posts[0]
    title = truncate_string(strip_tags((thread.message or "").replace("<br>", " ")), 50)
    return (
        200,
        {
            "title": title,
            "options": options,
            "captcha": captcha,
            "return_url": request_url,
            "reply_count": count_replies(session, thread_id),
            "thread": post_view(session, thread, is_thread_page=True),
            "posts": [
                post_view(session, post, is_thread_page=True) for post in posts[1:]
            ],
            "thread_id": thread_id,
            "page_kind": "thread",
        },
        None,
    )


def short_context(
    session: Session,
    options: BoardOption,
    captcha: dict[str, str],
    thread_id: int,
    request_url: str,
) -> tuple[int, dict[str, Any], str | None]:
    thread = session.scalar(
        select(Post).where(
            Post.id == thread_id, Post.parent == 0, Post.status == STATUS_ACTIVE
        )
    )
    reply_count = count_replies(session, thread_id)
    if not thread or reply_count < 100:
        return 302, {}, f"/thread/{thread_id}"
    replies = list(
        reversed(
            session.scalars(
                select(Post)
                .where(Post.parent == thread_id, Post.status == STATUS_ACTIVE)
                .order_by(desc(Post.id))
                .limit(50)
            ).all()
        )
    )
    title = truncate_string(strip_tags((thread.message or "").replace("<br>", " ")), 50)
    return (
        200,
        {
            "title": title,
            "options": options,
            "captcha": captcha,
            "return_url": request_url,
            "reply_count": reply_count,
            "thread": post_view(
                session, thread, is_thread_page=True, status=STATUS_OP_DELETED
            ),
            "posts": [
                post_view(session, post, is_thread_page=True, status=STATUS_OP_DELETED)
                for post in replies
            ],
            "thread_id": thread_id,
            "page_kind": "short",
            "omitted": reply_count - len(replies),
        },
        None,
    )


def catalog_context(session: Session, search: str = "") -> dict[str, Any]:
    search = search.strip()
    items = []
    for thread in get_threads(session):
        if search and not search_in_thread(session, thread.id, search):
            continue
        item = catalog_thread_view(session, thread, tabindex=len(items) + 1)
        if item:
            items.append(item)
    return {"title": "Каталог", "search": search, "threads": items}


def info_context(options: BoardOption) -> dict[str, Any]:
    return {
        "title": "Инфо",
        "max_file_size": readable_bytes(options.max_file_size),
        "bump_limit": options.bump_limit,
        "max_threads": options.max_threads,
    }


def archive_context(session: Session, page: int) -> tuple[int, dict[str, Any]]:
    page = max(0, page)
    threads_per_page = 50
    total_threads = (
        session.scalar(
            select(func.count())
            .select_from(Post)
            .where(Post.parent == 0, Post.status == STATUS_ARCHIVED)
        )
        or 0
    )
    if total_threads == 0:
        return 404, {}
    total_pages = max(1, math.ceil(total_threads / threads_per_page))
    if page >= total_pages:
        return 404, {}
    threads = get_threads(
        session,
        status=STATUS_ARCHIVED,
        limit=threads_per_page,
        offset=page * threads_per_page,
    )
    items = []
    for thread in threads:
        item = catalog_thread_view(
            session, thread, archived=True, tabindex=len(items) + 1
        )
        if item:
            items.append(item)
    return 200, {
        "title": "Архив",
        "pagination": pagination_items(page, total_pages, "/archive", "/archive"),
        "threads": items,
    }


def archived_thread_context(
    session: Session, thread_id: int
) -> tuple[int, dict[str, Any], str | None]:
    posts = list(
        session.scalars(
            select(Post)
            .where(
                (Post.id == thread_id) | (Post.parent == thread_id),
                Post.status.in_([STATUS_ACTIVE, STATUS_ARCHIVED]),
            )
            .order_by(Post.id)
        ).all()
    )
    if not posts or posts[0].parent != 0:
        return 404, {}, None
    if posts[0].status == STATUS_ACTIVE:
        return 302, {}, f"/thread/{thread_id}"
    thread = posts[0]
    title = truncate_string(strip_tags((thread.message or "").replace("<br>", " ")), 50)
    return (
        200,
        {
            "title": title,
            "reply_count": count_replies(session, thread_id),
            "thread": post_view(
                session, thread, is_thread_page=True, status=STATUS_ARCHIVED
            ),
            "posts": [
                post_view(session, post, is_thread_page=True, status=STATUS_ARCHIVED)
                for post in posts[1:]
            ],
            "thread_id": thread_id,
        },
        None,
    )


def modlog_context(session: Session, page: int) -> tuple[int, dict[str, Any]]:
    page = max(0, page)
    posts_per_page = 50
    total_posts = (
        session.scalar(
            select(func.count())
            .select_from(Post)
            .where(Post.status.in_([STATUS_ADMIN_DELETED, STATUS_OP_DELETED]))
        )
        or 0
    )
    total_pages = max(1, math.ceil(total_posts / posts_per_page))
    if page >= total_pages:
        return 404, {}
    deleted_posts = session.scalars(
        select(Post)
        .where(Post.status.in_([STATUS_ADMIN_DELETED, STATUS_OP_DELETED]))
        .order_by(desc(Post.id))
        .limit(posts_per_page)
        .offset(page * posts_per_page)
    ).all()
    entries = []
    for post in deleted_posts:
        is_thread = post.parent == 0
        deleted_by = (
            "администратором" if post.status == STATUS_ADMIN_DELETED else "ОП-ом"
        )
        thread_id = post.id if is_thread else post.parent
        thread_status = (
            post.status
            if is_thread
            else session.scalar(select(Post.status).where(Post.id == post.parent))
        )
        entries.append(
            {
                "is_thread": is_thread,
                "deleted_by": deleted_by,
                "thread_id": thread_id,
                "thread_status": thread_status,
                "post": post_view(
                    session, post, is_thread_page=True, status=STATUS_ADMIN_DELETED
                ),
            }
        )
    return 200, {
        "title": "Модлог",
        "pagination": pagination_items(page, total_pages, "/modlog", "/modlog"),
        "entries": entries,
    }


def manage_context(
    session: Session,
    options: BoardOption | None,
    page: int,
    manage_key: str,
    request_url: str,
) -> tuple[int, dict[str, Any]]:
    captcha_types = [("simple", "Простая"), ("shadow", "Тени")]
    if not options:
        return 200, {
            "title": "Управление",
            "setup_mode": True,
            "captcha_types": captcha_types,
            "manage_key": manage_key,
        }
    page = max(0, page)
    posts_per_page = 50
    total_posts = (
        session.scalar(
            select(func.count()).select_from(Post).where(Post.status == STATUS_ACTIVE)
        )
        or 0
    )
    total_pages = max(1, math.ceil(total_posts / posts_per_page))
    if page >= total_pages:
        page = total_pages - 1
    active_posts = session.scalars(
        select(Post)
        .where(Post.status == STATUS_ACTIVE)
        .order_by(desc(Post.id))
        .limit(posts_per_page)
        .offset(page * posts_per_page)
    ).all()
    stats = post_stats(session)
    entries = []
    for post in active_posts:
        entries.append(
            {
                "is_thread": post.parent == 0,
                "thread_id": post.id if post.parent == 0 else post.parent,
                "post": post_view(session, post),
            }
        )
    return 200, {
        "title": "Управление",
        "setup_mode": False,
        "options": options,
        "captcha_types": captcha_types,
        "manage_key": manage_key,
        "pagination": pagination_items(
            page, total_pages, "/manage", "/manage", f"?key={manage_key}"
        ),
        "return_url": request_url,
        "stats": stats,
        "entries": entries,
        "page": page,
    }


def api_page_context() -> dict[str, Any]:
    return {"title": "API"}
