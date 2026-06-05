"""FastAPI application entry point."""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import init_db
from .routers import model_keys, projects, scripts, validate

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
log = logging.getLogger("script_workshop")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Script Workshop",
        version="0.1.0",
        description="AI 小说转剧本工作台 — API",
    )

    # CORS for dev (vite/next on different port)
    origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in origins],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def _startup() -> None:  # noqa: D401
        init_db()
        log.info("DB initialized at %s", settings.database_url)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "version": app.version}

    @app.get("/api/healthz")
    def healthz_api() -> dict[str, str]:
        return {"status": "ok", "version": app.version}

    app.include_router(projects.router)
    app.include_router(scripts.router)
    app.include_router(model_keys.router)
    app.include_router(validate.router)
    return app


app = create_app()
