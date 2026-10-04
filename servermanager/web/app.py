"""The web layer: thin routes over the collectors.

No business logic lives here. Every route does three things: check the token,
call one collector, return its dict. When a collector reports an error the route
still answers 200 - the failure is data the UI is supposed to show, not an
exception to swallow.
"""

from __future__ import annotations

import secrets

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from servermanager import __version__
from servermanager.collectors import configure, containers, overview, ports, processes, services, system
from servermanager.config import Settings


def _supplied_token(request: Request, header_token: str | None, authorization: str | None, query_token: str | None) -> str:
    if header_token:
        return header_token
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    if query_token:
        return query_token
    return ""


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    configure(settings)

    app = FastAPI(
        title="Roans Server Manager",
        version=__version__,
        docs_url=None,
        redoc_url=None,
    )

    def require_token(
        request: Request,
        x_sm_token: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
        token: str | None = Query(default=None),
    ) -> None:
        """Gate /api/* on the shared secret, when one is configured.

        Without a secret the bind address is the only control, which is exactly
        as safe as it sounds - see AGENTS.md.
        """
        if not settings.token_required:
            return
        supplied = _supplied_token(request, x_sm_token, authorization, token)
        if not secrets.compare_digest(supplied, settings.token):
            raise HTTPException(
                status_code=401,
                detail="token required: send X-SM-Token, 'Authorization: Bearer <token>' or ?token=",
            )

    guard = [Depends(require_token)]

    @app.get("/healthz")
    def healthz() -> dict:
        return {
            "status": "ok",
            "ok": True,
            "version": __version__,
            "server": settings.server_name,
            "token_required": settings.token_required,
        }

    @app.get("/api/overview", dependencies=guard)
    def api_overview() -> dict:
        return overview(settings)

    @app.get("/api/system", dependencies=guard)
    def api_system() -> dict:
        return system.snapshot(settings)

    @app.get("/api/processes", dependencies=guard)
    def api_processes(limit: int = Query(default=40, ge=1, le=500)) -> dict:
        return processes.snapshot(settings, limit=limit)

    @app.get("/api/docker", dependencies=guard)
    def api_docker() -> dict:
        return containers.snapshot(settings)

    @app.get("/api/ports", dependencies=guard)
    def api_ports() -> dict:
        return ports.snapshot(settings)

    @app.get("/api/services", dependencies=guard)
    def api_services(limit: int = Query(default=60, ge=1, le=500)) -> dict:
        return services.snapshot(settings, limit=limit)

    @app.exception_handler(HTTPException)
    def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"ok": False, "status": exc.status_code, "error": exc.detail},
        )

    if settings.web_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(settings.web_dir), html=True), name="web")

    return app


app = create_app()
