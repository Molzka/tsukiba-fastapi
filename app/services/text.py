import html
import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from urllib.parse import unquote

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models import BoardOption, Post

URL_RE = re.compile(
    r"https?://[\w.-]+[\w](?:/(?:\([^<>\s]+\)|[^()<>\s]*[^()<>\s.,?:;\n])*)?"
)
POST_LINK_RE = re.compile(r"&gt;&gt;(\d+)")
MARKUP_RE = re.compile(
    r"\[(sp|s|i)\]((?:(?!\[/\1\]).)*?)\[/\1\]", re.IGNORECASE | re.DOTALL
)


def readable_bytes(bytes_count: int) -> str:
    if bytes_count == 0:
        return "0Б"
    sizes = ["Б", "Кб", "Мб", "Гб"]
    index = min(3, int(len(bin(bytes_count)) / 10))
    while index > 0 and bytes_count < 1024**index:
        index -= 1
    return f"{bytes_count / (1024**index):.2f}".rstrip("0").rstrip(".") + sizes[index]


def truncate_string(value: str, length: int) -> str:
    if len(value) <= length:
        return value
    truncated = value[:length]
    last_space = truncated.rfind(" ")
    if last_space != -1:
        truncated = truncated[:last_space]
    return truncated + "..."


def strip_combining_marks(value: str) -> str:
    return "".join(ch for ch in value if unicodedata.category(ch) != "Mn")


def post_exists(session: Session, post_id: int) -> bool:
    return (
        session.scalar(select(func.count()).select_from(Post).where(Post.id == post_id))
        > 0
    )


def transform_message(session: Session, message: str) -> str:
    message = html.escape(message, quote=True)
    message = strip_combining_marks(message)
    message = re.sub(r"[ \t]+", " ", message)

    link_count = 0

    def replace_post_link(match: re.Match[str]) -> str:
        nonlocal link_count
        if link_count >= 20:
            return match.group(0)
        post_id = int(match.group(1))
        if post_exists(session, post_id):
            link_count += 1
            return f"<post-link>&gt;&gt;{post_id}</post-link>"
        return match.group(0)

    message = POST_LINK_RE.sub(replace_post_link, message)
    message = re.sub(
        r"^&gt;(.*)$",
        lambda match: '<span class="quote">&gt;' + match.group(1).rstrip() + "</span>",
        message,
        flags=re.MULTILINE,
    ).strip()

    tags = {
        "sp": ("span", ' class="spoiler"'),
        "s": ("s", ""),
        "i": ("i", ""),
    }

    while True:
        next_message = MARKUP_RE.sub(
            lambda match: (
                f"<{tags[match.group(1).lower()][0]}{tags[match.group(1).lower()][1]}>{match.group(2)}</{tags[match.group(1).lower()][0]}>"
            ),
            message,
        )
        if next_message == message:
            break
        message = next_message

    message = message.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")

    def replace_url(match: re.Match[str]) -> str:
        url = match.group(0)
        decoded_url = html.escape(unquote(html.unescape(url)), quote=True)
        return f'<a href="{url}" target="_blank" rel="noreferrer nofollow">{decoded_url}</a>'

    return URL_RE.sub(replace_url, message)


def validate_message(session: Session, options: BoardOption, message: str) -> int:
    if len(message) > options.max_message_length:
        return 1
    if message.count("\n") > 100:
        return 2
    if len(message) >= 1000:
        words = re.split(r"\s+", message.lower())
        for word, count in Counter(words).items():
            if len(word) <= 2 or word.isnumeric():
                continue
            if count >= 100:
                return 2

    normalized = transform_message(session, message)[:100]
    deleted_messages = session.scalars(
        select(func.substr(Post.message, 1, 100))
        .where(Post.status == 1, func.length(Post.message) > 8)
        .order_by(desc(Post.id))
        .limit(500)
    ).all()
    for deleted_message in deleted_messages:
        if not deleted_message:
            continue
        if SequenceMatcher(None, normalized, deleted_message).ratio() > 0.9:
            return 2
    return 0


def strip_tags(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"<[^>]+>", "", value)
