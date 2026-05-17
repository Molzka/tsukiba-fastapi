from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import settings
from app.deps import error_response
from app.endpoints.actions import manage as manage_actions
from app.endpoints.actions import moderation, posts
from app.endpoints.api import board as api_board
from app.endpoints.pages import admin, board
from app.services.files import ensure_storage_dirs


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_storage_dirs()
    redis: Redis | None = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        await redis.ping()
    except RedisError:
        await redis.aclose()
        redis = None
    app.state.redis = redis
    try:
        yield
    finally:
        if redis is not None:
            await redis.aclose()


app = FastAPI(title="Tsukiba", lifespan=lifespan)
app.mount(
    "/assets",
    StaticFiles(directory=settings.assets_dir, check_dir=False),
    name="assets",
)
app.mount(
    "/media", StaticFiles(directory=settings.media_dir, check_dir=False), name="media"
)
app.mount(
    "/thumb", StaticFiles(directory=settings.thumb_dir, check_dir=False), name="thumb"
)

app.include_router(api_board.router)
app.include_router(manage_actions.router)
app.include_router(moderation.router)
app.include_router(posts.router)
app.include_router(admin.router)
app.include_router(board.router)


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"error": "Страница не найдена"}, status_code=404)
    return error_response(request)
