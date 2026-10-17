"""Separate judge authentication and anonymous browser-session authorization."""

import secrets

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader


COOKIE_NAME = "forte_session"
JUDGE_KEY = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_judge(request: Request, api_key: str | None = Security(JUDGE_KEY)):
    expected = request.app.state.settings.jury_api_key
    supplied = request.headers.get("X-API-Key", "")
    if not expected or not supplied or not secrets.compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(401, detail={"code": "unauthorized", "message": "A valid X-API-Key is required."})


def require_session(request: Request):
    session = request.app.state.store.session(request.cookies.get(COOKIE_NAME))
    if session is None:
        raise HTTPException(401, detail={"code": "session_required", "message": "Start a browser session before continuing."})
    return session


def require_same_origin(request: Request):
    origin = request.headers.get("origin")
    expected = request.app.state.settings.public_origin.rstrip("/") or str(request.base_url).rstrip("/")
    if origin and origin.rstrip("/") != expected:
        raise HTTPException(403, detail={"code": "origin_rejected", "message": "Cross-origin requests are not allowed."})
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, detail={"code": "origin_rejected", "message": "Cross-site requests are not allowed."})


def require_csrf(request: Request):
    require_same_origin(request)
    session = require_session(request)
    supplied = request.headers.get("X-CSRF-Token", "")
    if not supplied or not secrets.compare_digest(supplied.encode(), session["csrf"].encode()):
        raise HTTPException(403, detail={"code": "csrf_rejected", "message": "A valid session CSRF token is required."})
    return session


class BodyLimitMiddleware:
    """Enforce the upload budget while the multipart parser consumes the request."""

    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") != "POST":
            return await self.app(scope, receive, send)
        from starlette.responses import JSONResponse

        # Authenticate before multipart parsing can spool an uploaded file.
        request = Request(scope)
        try:
            if scope.get("path") == "/api/v1/analyze":
                require_judge(request)
            elif scope.get("path") == "/api/ui/analyze":
                require_csrf(request)
        except HTTPException as exc:
            return await JSONResponse({"detail": exc.detail}, status_code=exc.status_code)(scope, receive, send)

        headers = dict(scope.get("headers", []))
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            length = 0
        if length > self.max_bytes:
            return await JSONResponse({"detail": {"code": "upload_too_large", "message": "The upload exceeds the configured size limit."}}, status_code=413)(scope, receive, send)
        consumed = 0

        async def limited_receive():
            nonlocal consumed
            message = await receive()
            if message["type"] == "http.request":
                consumed += len(message.get("body", b""))
                if consumed > self.max_bytes:
                    raise HTTPException(413, detail={"code": "upload_too_large", "message": "The upload exceeds the configured size limit."})
            return message

        return await self.app(scope, limited_receive, send)
