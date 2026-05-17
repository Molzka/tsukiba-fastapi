import hashlib
import mimetypes
import random
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import BoardOption, Post
from app.services.text import readable_bytes

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/gif", "video/mp4", "video/webm"}
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "mp4", "webm"}
IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif"}
VIDEO_TYPES = {"video/mp4", "video/webm"}


@dataclass
class PreparedUpload:
    original_name: str
    content_type: str
    data: bytes
    extension: str
    digest: str


def get_subdir_path(file_hash: str) -> str:
    return file_hash[:2]


def extension_from_name(filename: str) -> str:
    extension = Path(filename).suffix.lower().lstrip(".")
    return "jpg" if extension == "jpeg" else extension


def content_type_for(upload: UploadFile, extension: str) -> str:
    if upload.content_type:
        return upload.content_type
    guessed, _ = mimetypes.guess_type(f"file.{extension}")
    return guessed or "application/octet-stream"


async def prepare_uploads(files: list[UploadFile] | None) -> list[PreparedUpload]:
    prepared: list[PreparedUpload] = []
    for upload in files or []:
        if not upload.filename:
            continue
        data = await upload.read()
        if not data:
            continue
        extension = extension_from_name(upload.filename)
        digest = hashlib.sha256(data).hexdigest()
        prepared.append(
            PreparedUpload(
                original_name=upload.filename,
                content_type=content_type_for(upload, extension),
                data=data,
                extension=extension,
                digest=digest,
            )
        )
    return prepared


def image_dimensions(data: bytes) -> tuple[int, int] | None:
    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
        with Image.open(BytesIO(data)) as image:
            return image.size
    except (OSError, UnidentifiedImageError):
        return None


def probe_video_file(path: Path) -> tuple[str, str] | None:
    try:
        resolution = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "csv=s=x:p=0",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        duration_raw = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nw=1:nk=1",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    if not resolution:
        return None
    try:
        seconds = int(float(duration_raw))
    except ValueError:
        seconds = 0
    duration = f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"
    return resolution, duration


def validate_video(data: bytes) -> tuple[str, str] | None:
    suffix = ".video"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    try:
        return probe_video_file(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)


def validate_files(
    session: Session, options: BoardOption, uploads: list[PreparedUpload], parent: int
) -> int:
    if not uploads:
        return 0 if parent != 0 else 1
    if len(uploads) > 4:
        return 2
    if sum(len(upload.data) for upload in uploads) > options.max_file_size:
        return 5

    upload_hashes = {upload.digest for upload in uploads}
    deleted_posts = session.execute(
        select(Post.file1, Post.file2, Post.file3, Post.file4)
        .where(Post.status == 1)
        .order_by(desc(Post.id))
        .limit(500)
    ).all()
    for deleted_post in deleted_posts:
        for filename in deleted_post:
            if filename and Path(filename).stem in upload_hashes:
                return 6

    for upload in uploads:
        if (
            upload.extension not in ALLOWED_EXTENSIONS
            or upload.content_type not in ALLOWED_TYPES
        ):
            return 3
        if upload.content_type in IMAGE_TYPES:
            if image_dimensions(upload.data) is None:
                return 4
        elif upload.content_type in VIDEO_TYPES:
            if validate_video(upload.data) is None:
                return 4
    return 0


def ensure_storage_dirs() -> None:
    settings.media_dir.mkdir(parents=True, exist_ok=True)
    settings.thumb_dir.mkdir(parents=True, exist_ok=True)


def create_image_thumbnail(data: bytes, destination: Path, max_size: int = 180) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(BytesIO(data)) as image:
        image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", image.size, (234, 234, 234))
        if image.mode in {"RGBA", "LA"}:
            canvas.paste(
                image.convert("RGBA"), mask=image.convert("RGBA").getchannel("A")
            )
        else:
            canvas.paste(image.convert("RGB"))
        canvas.save(destination, "WEBP", quality=50)


def create_video_thumbnail(
    source: Path, destination: Path, max_size: int = 180
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    probe = probe_video_file(source)
    if not probe:
        create_placeholder_thumbnail(destination)
        return
    resolution, duration = probe
    try:
        width, height = [int(value) for value in resolution.split("x", 1)]
        seconds = sum(
            int(part) * factor
            for part, factor in zip(duration.split(":"), [3600, 60, 1])
        )
    except ValueError:
        width, height, seconds = max_size, max_size, 1
    aspect = width / height if height else 1
    if width <= max_size and height <= max_size:
        thumb_width, thumb_height = width, height
    elif width > height:
        thumb_width, thumb_height = max_size, max(1, int(max_size / aspect))
    else:
        thumb_height, thumb_width = max_size, max(1, int(max_size * aspect))
    seek = f"{random.uniform(0, min(5, max(seconds, 1))):.3f}"
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                seek,
                "-i",
                str(source),
                "-vf",
                f"scale={thumb_width}:{thumb_height}:force_original_aspect_ratio=decrease",
                "-vframes",
                "1",
                str(destination),
            ],
            check=True,
            capture_output=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        create_placeholder_thumbnail(destination)


def create_placeholder_thumbnail(destination: Path) -> None:
    image = Image.new("RGB", (180, 100), (234, 234, 234))
    image.save(destination, "WEBP", quality=50)


def strip_metadata(path: Path) -> None:
    try:
        subprocess.run(
            ["exiftool", "-all=", "-overwrite_original", str(path)],
            check=False,
            capture_output=True,
        )
    except FileNotFoundError:
        return


def upload_files(uploads: list[PreparedUpload]) -> list[dict[str, str]]:
    ensure_storage_dirs()
    uploaded: list[dict[str, str]] = []
    for upload in uploads:
        filename = f"{upload.digest}.{upload.extension}"
        subdir = get_subdir_path(upload.digest)
        media_dir = settings.media_dir / subdir
        thumb_dir = settings.thumb_dir / subdir
        media_dir.mkdir(parents=True, exist_ok=True)
        thumb_dir.mkdir(parents=True, exist_ok=True)
        media_path = media_dir / filename
        thumb_path = thumb_dir / f"{upload.digest}.webp"

        if not media_path.exists():
            media_path.write_bytes(upload.data)
            strip_metadata(media_path)
            if upload.content_type in IMAGE_TYPES:
                create_image_thumbnail(media_path.read_bytes(), thumb_path)
            elif upload.content_type in VIDEO_TYPES:
                create_video_thumbnail(media_path, thumb_path)

        info = readable_bytes(media_path.stat().st_size)
        if upload.content_type in IMAGE_TYPES:
            dimensions = image_dimensions(media_path.read_bytes())
            if dimensions:
                info += f", {dimensions[0]}x{dimensions[1]}"
        elif upload.content_type in VIDEO_TYPES:
            video_info = probe_video_file(media_path)
            if video_info:
                info += f", {video_info[0]}, {video_info[1]}"
        uploaded.append({"name": filename, "info": info})
    return uploaded


def cleanup_files(session: Session) -> None:
    seven_days_ago = int(time.time()) - 60 * 60 * 24 * 7
    protected: set[str] = set()
    for row in session.execute(
        select(Post.file1, Post.file2, Post.file3, Post.file4).where(
            (Post.status == 0)
            | ((Post.status.in_([1, 2, 3])) & (Post.status_time >= seven_days_ago))
        )
    ):
        protected.update(filename for filename in row if filename)

    for row in session.execute(
        select(Post.file1, Post.file2, Post.file3, Post.file4).where(
            Post.status.in_([1, 2, 3]), Post.status_time < seven_days_ago
        )
    ):
        for filename in row:
            if not filename or filename in protected:
                continue
            file_hash = Path(filename).stem
            subdir = get_subdir_path(file_hash)
            media_path = settings.media_dir / subdir / filename
            thumb_path = settings.thumb_dir / subdir / f"{file_hash}.webp"
            media_path.unlink(missing_ok=True)
            if not any(
                (settings.media_dir / get_subdir_path(Path(name).stem) / name).exists()
                for name in protected
            ):
                thumb_path.unlink(missing_ok=True)


def copy_legacy_assets() -> None:
    settings.media_dir.mkdir(exist_ok=True)
    settings.thumb_dir.mkdir(exist_ok=True)
    for name in ("favicon.ico",):
        source = Path(name)
        if source.exists() and not (settings.assets_dir / name).exists():
            shutil.copyfile(source, settings.assets_dir / name)
