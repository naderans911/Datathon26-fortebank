"""Same-origin API/frontend entry point: uvicorn backend.app.main:app."""

import html
import json
from threading import BoundedSemaphore

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from backend.app.api.routes import router
from backend.app.core.config import Settings
from backend.app.core.security import BodyLimitMiddleware
from backend.app.db.store import Store


def create_app(settings: Settings | None = None, detector=None) -> FastAPI:
    settings = settings or Settings()
    if detector is None:
        from backend.app.detectors.factory import build_detector
        detector = build_detector(settings)
    app = FastAPI(title="Forte Cash Review", version="0.1.0",
                  description="Datathon prototype. Local video analysis; findings require human review.",
                  docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.store = Store(settings.database_path)
    app.state.detector = detector
    app.state.demo_slots = BoundedSemaphore(1)
    app.add_middleware(BodyLimitMiddleware, max_bytes=settings.max_upload_bytes + 1024 * 1024)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; media-src 'self' blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        return response

    app.include_router(router)

    @app.get("/docs", response_class=HTMLResponse, include_in_schema=False)
    def api_documentation():
        schema = app.openapi()
        routes = []
        for path, operations in schema["paths"].items():
            for method, operation in operations.items():
                if method not in {"get", "post", "delete", "put", "patch"}:
                    continue
                routes.append(f"<li><code>{html.escape(method.upper())} {html.escape(path)}</code> — {html.escape(operation.get('summary', ''))}</li>")
        return HTMLResponse("<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>Forte Cash Review API</title><style>body{font:16px system-ui;margin:3rem auto;max-width:1000px;padding:0 1rem;color:#20212a}"
            "h1{color:#4a0221}code,pre{font:14px monospace}li{margin:.8rem 0}pre{padding:1rem;background:#f1f2f5;overflow:auto}a{color:#a31551}</style>"
            "<h1>Forte Cash Review API</h1><p>Datathon prototype. Findings require human review.</p>"
            "<p>Judge requests require <code>X-API-Key</code>. Upload a multipart <code>file</code> to <code>POST /api/v1/analyze</code>; "
            "poll <code>GET /api/v1/jobs/{job_id}</code>. The generated OpenAPI schema below defines exact request and response shapes.</p>"
            "<p><a href='/openapi.json'>Download OpenAPI JSON</a> · <a href='/'>Application</a></p><ul>"
            + "".join(routes) + "</ul><h2>Generated schema</h2><pre>"
            + html.escape(json.dumps(schema, indent=2, ensure_ascii=False)) + "</pre></html>")

    @app.get("/healthz", include_in_schema=False)
    def healthz():
        return {"status": "ok"}

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, detail="Not found")
        root = settings.frontend_dist.resolve()
        candidate = (root / path).resolve()
        if candidate.is_relative_to(root) and candidate.is_file():
            return FileResponse(candidate)
        index = root / "index.html"
        if index.is_file():
            return FileResponse(index)
        raise HTTPException(404, detail="Frontend build unavailable. Build frontend/dist or use the Vite development server.")

    return app


app = create_app()
