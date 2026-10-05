import hashlib
import json
import math
import mimetypes
import shutil
import subprocess
import tempfile
import time
import warnings
from dataclasses import dataclass
from contextlib import contextmanager
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
MAX_FILES = 4
UPLOAD_CHUNK_SIZE = 64 * 1024
SIZE_ERROR = "Общий размер прикреплённых файлов превышает лимит"


class UploadError(ValueError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


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


async def prepare_uploads(
    files: list[UploadFile] | None, *, max_total_size: int
) -> list[PreparedUpload]:
    prepared: list[PreparedUpload] = []
    uploads = [upload for upload in files or [] if upload.filename]
    if len(uploads) > MAX_FILES:
        raise UploadError("Разрешено прикрепление не более 4 файлов")
    remaining = max_total_size
    for upload in uploads:
        if upload.size is not None and upload.size > remaining:
            raise UploadError(SIZE_ERROR, 413)
        buffer = bytearray()
        while True:
            chunk = await upload.read(min(UPLOAD_CHUNK_SIZE, remaining + 1))
            if not chunk:
                break
            remaining -= len(chunk)
            if remaining < 0:
                raise UploadError(SIZE_ERROR, 413)
            buffer.extend(chunk)
        data = bytes(buffer)
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
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                image.verify()
            with Image.open(BytesIO(data)) as image:
                return image.size
    except (
        OSError,
        SyntaxError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        return None


def run_media_command(
    command: list[str], *, text: bool = False
) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE if text else subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=text,
            timeout=settings.media_process_timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise UploadError(
            "Превышено время обработки файла. Попробуйте файл меньшего размера", 504
        ) from exc
    except FileNotFoundError as exc:
        raise UploadError(
            "Обработчик медиа недоступен. Обратитесь к администратору", 503
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise UploadError(
            "Не удалось обработать файл. Проверьте его формат и целостность"
        ) from exc


def probe_video_file(path: Path) -> tuple[str, str] | None:
    result = run_media_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height:format=duration",
            "-of",
            "json",
            str(path),
        ],
        text=True,
    )
    try:
        metadata = json.loads(result.stdout)
        stream = metadata["streams"][0]
        width, height = int(stream["width"]), int(stream["height"])
        seconds_raw = float(metadata.get("format", {}).get("duration", 0))
        if (
            width <= 0
            or height <= 0
            or not math.isfinite(seconds_raw)
            or seconds_raw < 0
        ):
            return None
        seconds = int(seconds_raw)
    except (ValueError, TypeError, KeyError, IndexError):
        return None
    resolution = f"{width}x{height}"
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
    if len(uploads) > MAX_FILES:
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
        raise UploadError("Прикреплён повреждённый видеофайл")
    resolution, _ = probe
    width, height = [int(value) for value in resolution.split("x", 1)]
    aspect = width / height
    if width <= max_size and height <= max_size:
        thumb_width, thumb_height = width, height
    elif width > height:
        thumb_width, thumb_height = max_size, max(1, int(max_size / aspect))
    else:
        thumb_height, thumb_width = max_size, max(1, int(max_size * aspect))
    run_media_command(
        [
            "ffmpeg",
            "-nostdin",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            "0",
            "-protocol_whitelist",
            "file,pipe",
            "-i",
            str(source),
            "-vf",
            f"scale={thumb_width}:{thumb_height}:force_original_aspect_ratio=decrease",
            "-vframes",
            "1",
            str(destination),
        ]
    )
    if not destination.is_file() or destination.stat().st_size == 0:
        raise UploadError("Не удалось создать миниатюру видеофайла")


def strip_metadata(path: Path) -> None:
    if path.suffix.lower() != ".webm" and shutil.which("exiftool"):
        run_media_command(["exiftool", "-all=", "-overwrite_original", str(path)])


@dataclass
class StagedFiles:
    uploaded: list[dict[str, str]]
    pending: dict[Path, Path]
    created: list[Path]

    def publish(self) -> None:
        for destination, source in self.pending.items():
            if destination.exists():
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            source.replace(destination)
            self.created.append(destination)


@contextmanager
def stage_uploads(uploads: list[PreparedUpload]):
    staged = StagedFiles(uploaded=[], pending={}, created=[])
    try:
        ensure_storage_dirs()
        with (
            tempfile.TemporaryDirectory(dir=settings.media_dir) as staging,
            tempfile.TemporaryDirectory(dir=settings.thumb_dir) as thumb_staging,
        ):
            for upload in uploads:
                filename = f"{upload.digest}.{upload.extension}"
                subdir = get_subdir_path(upload.digest)
                media_path = settings.media_dir / subdir / filename
                thumb_path = settings.thumb_dir / subdir / f"{upload.digest}.webp"
                source = Path(staging) / filename
                staged_thumb = Path(thumb_staging) / f"{filename}.webp"
                source.write_bytes(upload.data)
                strip_metadata(source)
                if upload.content_type in IMAGE_TYPES:
                    create_image_thumbnail(source.read_bytes(), staged_thumb)
                else:
                    create_video_thumbnail(source, staged_thumb)
                staged.pending[thumb_path] = staged_thumb
                staged.pending[media_path] = source

                info = readable_bytes(source.stat().st_size)
                if upload.content_type in IMAGE_TYPES:
                    dimensions = image_dimensions(source.read_bytes())
                    if dimensions:
                        info += f", {dimensions[0]}x{dimensions[1]}"
                else:
                    video_info = probe_video_file(source)
                    if video_info:
                        info += f", {video_info[0]}, {video_info[1]}"
                staged.uploaded.append({"name": filename, "info": info})

            try:
                yield staged
            except Exception:
                for path in reversed(staged.created):
                    path.unlink(missing_ok=True)
                raise
    except (
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise UploadError(
            "Не удалось сохранить или обработать файл. Попробуйте другой файл"
        ) from exc


def upload_files(uploads: list[PreparedUpload]) -> list[dict[str, str]]:
    with stage_uploads(uploads) as staged:
        staged.publish()
        return staged.uploaded


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
