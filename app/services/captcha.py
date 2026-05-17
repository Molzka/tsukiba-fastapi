import base64
import hashlib
import hmac
import random
import secrets
import time
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from redis.asyncio import Redis

from app.config import settings
from app.models import BoardOption

CAPTCHA_LETTERS = "абвгдежзиклмнопрстуфхцчшщыьэюя"


def generate_captcha_code() -> str:
    return "".join(random.choice(CAPTCHA_LETTERS) for _ in range(random.randint(3, 4)))


def _font() -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_path = Path(settings.assets_dir) / "font.ttf"
    try:
        return ImageFont.truetype(str(font_path), 14)
    except OSError:
        return ImageFont.load_default()


def captcha_image(captcha_code: str, captcha_type: str) -> str:
    width, height = 69, 20
    background = (221, 221, 221)
    text = (51, 51, 51)
    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)
    font = _font()
    char_width = 16

    for index, char in enumerate(captcha_code):
        char_image = Image.new("RGBA", (char_width + 8, height + 8), (0, 0, 0, 0))
        char_draw = ImageDraw.Draw(char_image)
        char_draw.text((4, random.randint(0, 4)), char, font=font, fill=text)
        char_image = char_image.rotate(
            random.randint(-10, 10), resample=Image.Resampling.BICUBIC, expand=1
        )
        x = 5 + index * char_width
        y = random.randint(-2, 2)
        if captcha_type == "shadow":
            draw.text((x + random.choice([-1, 1]), y + 2), char, font=font, fill=text)
            draw.text((x, y + 1), char, font=font, fill=background)
        else:
            image.paste(char_image.convert("RGB"), (x, y), char_image)

    if captcha_type == "shadow":
        for _ in range(100):
            draw.point(
                (random.randint(0, width - 1), random.randint(0, height - 1)),
                fill=background,
            )

    buffer = BytesIO()
    try:
        image.save(buffer, format="WEBP", quality=50)
        mime = "image/webp"
    except OSError:
        image.save(buffer, format="PNG")
        mime = "image/png"
    return f"data:{mime};base64,{base64.b64encode(buffer.getvalue()).decode()}"


def fallback_verify_token(code: str, password_hash: str) -> str:
    hour = time.strftime("%Y%m%d%H")
    digest = hmac.new(
        settings.captcha_secret.encode(),
        f"{code.lower()}:{password_hash}:{hour}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"hmac:{digest}"


async def issue_captcha(redis: Redis | None, options: BoardOption) -> dict[str, str]:
    code = generate_captcha_code()
    token = secrets.token_urlsafe(32)
    if redis is not None:
        await redis.setex(
            f"captcha:{token}", settings.captcha_ttl_seconds, code.lower()
        )
    else:
        token = fallback_verify_token(code, options.password_hash)
    return {
        "captcha_image": captcha_image(code, options.captcha),
        "verify": token,
    }


async def validate_captcha(
    redis: Redis | None, options: BoardOption, captcha: str, verify: str
) -> bool:
    captcha = captcha.lower().strip()
    if redis is not None:
        key = f"captcha:{verify}"
        stored = await redis.get(key)
        if stored is None:
            return False
        if secrets.compare_digest(str(stored), captcha):
            await redis.delete(key)
            return True
        return False
    return secrets.compare_digest(
        verify, fallback_verify_token(captcha, options.password_hash)
    )
