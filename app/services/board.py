import random
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, desc, func, or_, select, update
from sqlalchemy.orm import Session, aliased

from app.config import settings
from app.models import BoardOption, Post
from app.security import hash_password, verify_password
from app.services.files import cleanup_files, upload_files, validate_files
from app.services.text import transform_message, validate_message

STATUS_ACTIVE = 0
STATUS_ADMIN_DELETED = 1
STATUS_OP_DELETED = 2
STATUS_ARCHIVED = 3


def get_options(session: Session) -> BoardOption | None:
    return session.scalar(select(BoardOption).order_by(desc(BoardOption.id)).limit(1))


def board_is_setup(session: Session) -> bool:
    return get_options(session) is not None


def create_options(
    session: Session,
    *,
    max_file_size_mb: int,
    bump_limit: int,
    max_threads: int,
    max_message_length: int,
    captcha: str,
    stop_board: bool,
    password: str,
    post_id_seed: int = 0,
) -> BoardOption:
    option = BoardOption(
        id=1,
        max_file_size=max_file_size_mb * 1024 * 1024,
        bump_limit=bump_limit,
        max_threads=max_threads,
        max_message_length=max_message_length,
        captcha=captcha,
        stop_board=stop_board,
        password_hash=hash_password(password),
        post_id_seed=post_id_seed,
    )
    session.add(option)
    session.commit()
    return option


def update_options(
    session: Session,
    options: BoardOption,
    *,
    max_file_size_mb: int,
    bump_limit: int,
    max_threads: int,
    max_message_length: int,
    captcha: str,
    stop_board: bool,
    new_password: str | None = None,
) -> BoardOption:
    options.max_file_size = max_file_size_mb * 1024 * 1024
    options.bump_limit = bump_limit
    options.max_threads = max_threads
    options.max_message_length = max_message_length
    options.captcha = captcha
    options.stop_board = stop_board
    if new_password:
        options.password_hash = hash_password(new_password)
    session.commit()
    return options


def get_threads(
    session: Session,
    *,
    status: int = STATUS_ACTIVE,
    limit: int | None = None,
    offset: int = 0,
) -> list[Post]:
    replies = aliased(Post)
    last_bump = func.max(
        case(
            (replies.sage.is_(True), Post.id), else_=func.coalesce(replies.id, Post.id)
        )
    ).label("last_bump")
    statement = (
        select(Post)
        .outerjoin(replies, and_(Post.id == replies.parent, replies.status == status))
        .where(Post.parent == 0, Post.status == status)
        .group_by(Post.id)
        .order_by(desc(last_bump))
    )
    if limit is not None and limit > 0:
        statement = statement.limit(limit).offset(offset)
    return list(session.scalars(statement).all())


def count_replies(session: Session, thread_id: int) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(Post)
            .where(
                Post.parent == thread_id,
                Post.status.in_([STATUS_ACTIVE, STATUS_ARCHIVED]),
            )
        )
        or 0
    )


def get_replies_to_post(session: Session, post_id: int, thread_id: int) -> list[Post]:
    marker = f"<post-link>&gt;&gt;{post_id}</post-link>"
    return list(
        session.scalars(
            select(Post)
            .where(
                Post.parent == thread_id,
                Post.status.in_([STATUS_ACTIVE, STATUS_ARCHIVED]),
                Post.message.contains(marker),
            )
            .order_by(Post.id)
        ).all()
    )


def search_in_thread(session: Session, thread_id: int, search_text: str) -> bool:
    message = session.scalar(
        select(Post.message).where(
            Post.id == thread_id, Post.parent == 0, Post.status == STATUS_ACTIVE
        )
    )
    return bool(message and search_text.lower() in message.lower())


def get_thread_posts(
    session: Session, thread_id: int, statuses: tuple[int, ...] = (STATUS_ACTIVE,)
) -> list[Post]:
    return list(
        session.scalars(
            select(Post)
            .where(
                or_(Post.id == thread_id, Post.parent == thread_id),
                Post.status.in_(statuses),
            )
            .order_by(Post.id)
        ).all()
    )


def get_active_thread_posts(session: Session, thread_id: int) -> list[Post]:
    return get_thread_posts(session, thread_id, (STATUS_ACTIVE, STATUS_ARCHIVED))


def get_post_info(session: Session, post_id: int) -> Post | None:
    return session.scalar(
        select(Post).where(Post.id == post_id, Post.status == STATUS_ACTIVE)
    )


def sanitize_post(post: Post, *, include_parent: bool = False) -> dict[str, object]:
    result: dict[str, object] = {
        "id": post.id,
        "sage": int(post.sage),
        "time": post.time,
        "message": post.message,
        "file1": post.file1,
        "file1_info": post.file1_info,
        "file2": post.file2,
        "file2_info": post.file2_info,
        "file3": post.file3,
        "file3_info": post.file3_info,
        "file4": post.file4,
        "file4_info": post.file4_info,
    }
    if include_parent:
        result["parent"] = post.parent
    return result


def get_active_threads_list(session: Session) -> list[dict[str, object]]:
    threads = []
    for thread in get_threads(session):
        item = sanitize_post(thread)
        item["replies"] = count_replies(session, thread.id)
        item["opmod"] = 1 if thread.password_hash else None
        threads.append(item)
    return threads


def next_post_id(session: Session, options: BoardOption) -> int:
    current_max = session.scalar(select(func.max(Post.id)))
    return int(current_max or options.post_id_seed) + 1


def display_time() -> str:
    timestamp = datetime.now(ZoneInfo(settings.timezone)).strftime("%d/%m/%y %H:%M")
    return timestamp[:-1] + "X"


def throttled_status_time(session: Session, parent: int) -> int | str:
    now = int(time.time())
    if parent:
        status_time = int(f"{str(now)[:-1]}0")
        exists = session.scalar(
            select(func.count())
            .select_from(Post)
            .where(Post.status_time == status_time, Post.parent != 0)
        )
    else:
        status_time = int(f"{str(now)[:-2]}00")
        exists = session.scalar(
            select(func.count())
            .select_from(Post)
            .where(Post.status_time == status_time, Post.parent == 0)
        )
    if exists:
        return "Скорость постинга ограничена"
    return status_time


def manage_thread_statuses(
    session: Session, options: BoardOption | None = None
) -> None:
    options = options or get_options(session)
    if not options or options.max_threads <= 0:
        return

    active_threads = get_threads(session, status=STATUS_ACTIVE)
    status_time = int(f"{str(int(time.time()))[:-3]}000")
    archive_ids = [thread.id for thread in active_threads[options.max_threads :]]
    if archive_ids:
        session.execute(
            update(Post)
            .where(
                or_(Post.id.in_(archive_ids), Post.parent.in_(archive_ids)),
                Post.status == STATUS_ACTIVE,
            )
            .values(status=STATUS_ARCHIVED, status_time=status_time)
        )

    active_count = int(
        session.scalar(
            select(func.count())
            .select_from(Post)
            .where(Post.parent == 0, Post.status == STATUS_ACTIVE)
        )
        or 0
    )
    free_slots = max(0, options.max_threads - active_count)
    if free_slots:
        archived_threads = get_threads(
            session, status=STATUS_ARCHIVED, limit=free_slots
        )
        activate_ids = [thread.id for thread in archived_threads]
        if activate_ids:
            session.execute(
                update(Post)
                .where(
                    or_(Post.id.in_(activate_ids), Post.parent.in_(activate_ids)),
                    Post.status == STATUS_ARCHIVED,
                )
                .values(status=STATUS_ACTIVE, status_time=status_time)
            )
    session.commit()


def plain_reply_has_content(message: str) -> bool:
    return bool(re.sub(r"\[(s|sp|i)\]([^\[]*)\[/\1\]", r"\2", message).strip())


def submit_post(
    session: Session,
    options: BoardOption,
    *,
    parent: int,
    message: str,
    uploads: list,
    password: str | None = None,
    sage: bool = False,
    verify: str | None = None,
) -> int | str:
    if options.stop_board:
        return "Постинг приостановлен"
    if verify:
        already_used = session.scalar(
            select(func.count()).select_from(Post).where(Post.verify == verify)
        )
        if already_used:
            return "Капча уже использована"
    if password and len(password) > 100:
        return "Пароль не должен превышать 100 символов"
    if parent:
        parent_exists = session.scalar(
            select(func.count())
            .select_from(Post)
            .where(Post.id == parent, Post.parent == 0, Post.status == STATUS_ACTIVE)
        )
        if not parent_exists:
            return "Такого треда не существует"
        if not plain_reply_has_content(message) and not uploads:
            return "Ответ должен содержать сообщение или файл"

    message_validation = validate_message(session, options, message)
    if message_validation:
        return {
            1: "Ваше сообщение превышает лимит символов",
            2: "Ваш пост не прошёл фильтр от вайпа",
        }[message_validation]

    file_validation = validate_files(session, options, uploads, parent)
    if file_validation:
        return {
            1: "Для создания треда нужно прикрепить файл",
            2: "Разрешено прикрепление не более 4 файлов",
            3: "Поддерживаются только файлы формата: JPG, PNG, GIF, MP4 и WEBM",
            4: "Прикреплён повреждённый файл или произошла ошибка при загрузке",
            5: "Общий размер прикреплённых файлов превышает лимит",
            6: "Ваш пост не прошёл фильтр от вайпа",
        }[file_validation]

    status_time = throttled_status_time(session, parent)
    if isinstance(status_time, str):
        return status_time

    uploaded_files = upload_files(uploads)
    post_id = next_post_id(session, options)

    if parent:
        replies_count = int(
            session.scalar(
                select(func.count())
                .select_from(Post)
                .where(Post.parent == parent, Post.status == STATUS_ACTIVE)
            )
            or 0
        )
        if replies_count >= options.bump_limit:
            sage = True

    post = Post(
        id=post_id,
        parent=parent,
        sage=sage,
        time=display_time(),
        message=transform_message(session, message) if message else None,
        file1=uploaded_files[0]["name"] if len(uploaded_files) > 0 else None,
        file1_info=uploaded_files[0]["info"] if len(uploaded_files) > 0 else None,
        file2=uploaded_files[1]["name"] if len(uploaded_files) > 1 else None,
        file2_info=uploaded_files[1]["info"] if len(uploaded_files) > 1 else None,
        file3=uploaded_files[2]["name"] if len(uploaded_files) > 2 else None,
        file3_info=uploaded_files[2]["info"] if len(uploaded_files) > 2 else None,
        file4=uploaded_files[3]["name"] if len(uploaded_files) > 3 else None,
        file4_info=uploaded_files[3]["info"] if len(uploaded_files) > 3 else None,
        status=STATUS_ACTIVE,
        status_time=int(status_time),
        password_hash=hash_password(password) if parent == 0 and password else None,
        verify=verify,
    )
    session.add(post)
    session.flush()

    recent_verify_ids = (
        select(Post.id)
        .where(Post.verify.is_not(None))
        .order_by(desc(Post.id))
        .limit(100)
    )
    session.execute(
        update(Post)
        .where(Post.verify.is_not(None), Post.id.not_in(recent_verify_ids))
        .values(verify=None)
    )
    session.commit()
    manage_thread_statuses(session, options)
    if random.randint(1, 100) == 1:
        cleanup_files(session)
    return post_id


def moderate_posts(session: Session, post_ids: list[int], password: str) -> bool:
    options = get_options(session)
    if not options:
        return False
    status_time = int(f"{str(int(time.time()))[:-3]}000")
    moderated = False
    if verify_password(password, options.password_hash):
        session.execute(
            update(Post)
            .where(or_(Post.id.in_(post_ids), Post.parent.in_(post_ids)))
            .values(status=STATUS_ADMIN_DELETED, status_time=status_time)
        )
        moderated = True
    else:
        for post_id in post_ids:
            post = session.get(Post, post_id)
            if not post:
                continue
            if post.parent == 0:
                if verify_password(password, post.password_hash):
                    session.execute(
                        update(Post)
                        .where(or_(Post.id == post_id, Post.parent == post_id))
                        .values(status=STATUS_OP_DELETED, status_time=status_time)
                    )
                    moderated = True
            else:
                thread = session.get(Post, post.parent)
                if thread and verify_password(password, thread.password_hash):
                    session.execute(
                        update(Post)
                        .where(Post.id == post_id)
                        .values(status=STATUS_OP_DELETED, status_time=status_time)
                    )
                    moderated = True
    if moderated:
        session.commit()
        manage_thread_statuses(session, options)
    return moderated


def restore_posts(session: Session, post_ids: list[int], password: str) -> int:
    options = get_options(session)
    if not options:
        return 0
    restored_count = 0
    is_admin = verify_password(password, options.password_hash)
    for post_id in post_ids:
        post = session.get(Post, post_id)
        if not post:
            continue
        can_restore = is_admin
        if not can_restore and post.parent == 0 and post.status == STATUS_OP_DELETED:
            can_restore = verify_password(password, post.password_hash)
        elif not can_restore and post.parent != 0:
            parent_thread = session.get(Post, post.parent)
            can_restore = bool(
                parent_thread and verify_password(password, parent_thread.password_hash)
            )
        if not can_restore:
            continue
        if post.parent == 0:
            session.execute(
                update(Post)
                .where(or_(Post.id == post_id, Post.parent == post_id))
                .values(status=STATUS_ACTIVE)
            )
            restored_count += 1
        else:
            parent_status = session.scalar(
                select(Post.status).where(Post.id == post.parent)
            )
            if parent_status == STATUS_ACTIVE:
                session.execute(
                    update(Post).where(Post.id == post_id).values(status=STATUS_ACTIVE)
                )
                restored_count += 1
    if restored_count:
        session.commit()
        manage_thread_statuses(session, options)
    return restored_count


def post_stats(session: Session) -> dict[str, float]:
    now = int(time.time())
    raw_times = session.scalars(
        select(Post.time).where(Post.status.in_([STATUS_ACTIVE, STATUS_ARCHIVED]))
    ).all()
    parsed_times = []
    for value in raw_times:
        try:
            parsed_times.append(
                datetime.strptime(value.replace("X", "0"), "%d/%m/%y %H:%M").timestamp()
            )
        except ValueError:
            continue
    last_month = len(
        [stamp for stamp in parsed_times if stamp >= now - 60 * 60 * 24 * 30]
    )
    return {
        "lastHour": len([stamp for stamp in parsed_times if stamp >= now - 60 * 60]),
        "lastDay": len(
            [stamp for stamp in parsed_times if stamp >= now - 60 * 60 * 24]
        ),
        "avgPerHour": round(last_month / (24 * 30), 1),
        "avgPerDay": round(last_month / 30, 1),
    }
