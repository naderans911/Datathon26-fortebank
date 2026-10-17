"""Opt-in loopback-only annotation server. Do not mount in the judging app."""
import hashlib
import hmac
import ipaddress
import os
import secrets
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse

from .models import Annotation
from .store import ReviewError, ReviewStore, RevisionConflict

COOKIE = "forte_local_review"


@dataclass
class ReviewSettings:
    enabled: bool = False
    labels: Path = Path("reports/training/labels-validation.json")
    video_root: Path = Path("data/videos")
    data_dir: Path = Path("data/annotations")
    frontend_dist: Path = Path("frontend/dist")
    ffmpeg_binary: str = "ffmpeg"

    @classmethod
    def from_env(cls):
        return cls(enabled=os.getenv("ENABLE_LOCAL_REVIEW", "false").lower() == "true",
                   labels=Path(os.getenv("LOCAL_REVIEW_LABELS", "reports/training/labels-validation.json")),
                   video_root=Path(os.getenv("LOCAL_REVIEW_VIDEO_ROOT", "data/videos")),
                   data_dir=Path(os.getenv("LOCAL_REVIEW_DATA_DIR", "data/annotations")),
                   frontend_dist=Path(os.getenv("FRONTEND_DIST", "frontend/dist")),
                   ffmpeg_binary=os.getenv("FFMPEG_BINARY", "ffmpeg"))


def is_loopback(host):
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def create_app(settings: ReviewSettings | None = None):
    settings = settings or ReviewSettings.from_env()
    app = FastAPI(title="Local annotation workspace", docs_url=None, redoc_url=None, openapi_url=None)
    secret = secrets.token_bytes(32)
    preview_lock = threading.Lock()
    store = ReviewStore(settings.labels, settings.video_root, settings.data_dir) if settings.enabled else None
    app.state.review_store = store

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        try:
            host = urlsplit("//" + request.headers.get("host", "")).hostname or ""
        except ValueError:
            host = ""
        client = request.client.host if request.client else ""
        forwarded = any(name.lower() == "forwarded" or name.lower().startswith("x-forwarded-")
                        for name in request.headers)
        origin = request.headers.get("origin")
        expected_origin = f"{request.url.scheme}://{request.headers.get('host', '')}"
        if (not settings.enabled or not is_loopback(host) or not is_loopback(client) or forwarded
                or (origin is not None and origin != expected_origin)
                or (request.method not in {"GET", "HEAD"} and origin != expected_origin)
                or request.headers.get("sec-fetch-site") == "cross-site"):
            return JSONResponse({"detail": "Local review is available only on its enabled loopback server."}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request, _error):
        # Never echo private annotations or source paths in validation errors.
        return JSONResponse({"detail": "Check annotation fields, event boundaries and review statuses."}, status_code=422)

    @app.exception_handler(ReviewError)
    async def review_error(_request, error):
        return JSONResponse({"detail": str(error)}, status_code=409 if isinstance(error, RevisionConflict) else 422)

    def signed(value):
        return hmac.new(secret, value.encode(), hashlib.sha256).hexdigest()

    def require_session(request: Request):
        token = request.cookies.get(COOKIE, "")
        try:
            value, signature = token.rsplit(".", 1)
            expires = int(value.split(".", 1)[0])
            if expires < time.time() or not hmac.compare_digest(signature, signed(value)):
                raise ValueError
        except ValueError:
            raise HTTPException(401, "Open a local review session first.") from None
        return token

    def require_csrf(request: Request, token=Depends(require_session)):
        if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), signed("csrf:" + token)):
            raise HTTPException(403, "Refresh the local review session before saving.")

    def require_item(record_id):
        try:
            return store.item(record_id)
        except KeyError:
            raise HTTPException(404, "Review record not found.") from None

    @app.get("/api/review/session")
    def session(response: Response):
        value = f"{int(time.time()) + 86400}.{secrets.token_hex(24)}"
        token = f"{value}.{signed(value)}"
        response.set_cookie(COOKIE, token, max_age=86400, httponly=True, samesite="strict", path="/api/review")
        return {"csrf_token": signed("csrf:" + token)}

    @app.get("/api/review/items", dependencies=[Depends(require_session)])
    def items():
        return {"items": [store.summary(record_id) for record_id in store.records], "excluded_count": store.excluded}

    @app.get("/api/review/items/{record_id}", dependencies=[Depends(require_session)])
    def detail(record_id: str):
        require_item(record_id)
        return store.detail(record_id)

    @app.put("/api/review/items/{record_id}/annotation", dependencies=[Depends(require_csrf)])
    def save(record_id: str, annotation: Annotation):
        require_item(record_id)
        return {"annotation": store.save(record_id, annotation).model_dump()}

    @app.get("/api/review/items/{record_id}/video", dependencies=[Depends(require_session)])
    def video(record_id: str):
        require_item(record_id)
        try:
            source = store.video(record_id)
            metadata = source.stat()
        except (OSError, ReviewError):
            raise HTTPException(404, "The matched local video is unavailable.") from None
        cache_id = hashlib.sha256(f"{record_id}:{metadata.st_mtime_ns}:{metadata.st_size}".encode()).hexdigest()
        cache = settings.data_dir / ".previews" / f"{cache_id}.mp4"
        if not cache.exists():
            with preview_lock:
                if not cache.exists():
                    cache.parent.mkdir(parents=True, exist_ok=True)
                    temporary = cache.with_suffix(".partial.mp4")
                    command = [settings.ffmpeg_binary, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                               "-protocol_whitelist", "file,pipe", "-i", str(source), "-map", "0:v:0", "-an",
                               "-vf", "scale='min(1280,iw)':-2", "-c:v", "libx264", "-preset", "veryfast",
                               "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(temporary)]
                    try:
                        subprocess.run(command, check=True, timeout=180, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                        if not temporary.exists() or temporary.stat().st_size == 0:
                            raise OSError
                        os.replace(temporary, cache)
                    except (OSError, subprocess.SubprocessError):
                        temporary.unlink(missing_ok=True)
                        raise HTTPException(503, "The local browser preview could not be prepared. Check FFmpeg and the matched video.") from None
        return FileResponse(cache, media_type="video/mp4")

    @app.get("/{path:path}")
    def frontend(path: str):
        root = settings.frontend_dist.resolve()
        candidate = (root / path).resolve()
        if path.startswith("api/"):
            raise HTTPException(404)
        if candidate.is_relative_to(root) and candidate.is_file():
            return FileResponse(candidate)
        index = root / "index.html"
        if index.exists():
            return FileResponse(index)
        raise HTTPException(503, "Build the frontend before opening local review.")

    return app
