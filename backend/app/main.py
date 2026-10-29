from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.core.cache import get_cache
from app.core.config import get_settings
from app.core.logging import log_event, setup_logging
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.routers import admin, auth, discovery, driver, matches, me, messages, payments, ratings, ride_groups, ride_requests, rides
from app.services import payment_service, platform_settings, route_service
from app.services.state_machine import InvalidTransition


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    setup_logging()
    if s.sentry_dsn:  # error monitoring is opt-in
        import sentry_sdk

        sentry_sdk.init(dsn=s.sentry_dsn, traces_sample_rate=0.1)
    if s.database_url.startswith("sqlite"):  # zero-setup dev; Postgres deployments use `alembic upgrade head`
        import app.models  # noqa: F401

        Base.metadata.create_all(engine)
    route_service.set_route_cache(get_cache())
    with SessionLocal() as db:
        platform_settings.apply_from_db(db)
    log_event("app.started", environment=s.environment, routing=s.routing_provider, payments=payment_service.get_gateway().name)
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="ShareTaxi API", version="0.1.0", lifespan=lifespan,
                  description="Collaborative ride matching: post where you're going, we group people going your way.")
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins, allow_methods=["*"], allow_headers=["*"])

    for r in (auth.router, ride_requests.router, driver.router, matches.router, ride_groups.router, rides.router, payments.router,
              messages.router, ratings.router, discovery.router, me.router, admin.router):
        app.include_router(r)

    @app.exception_handler(InvalidTransition)
    async def _invalid(_: Request, exc: InvalidTransition):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.get("/health", tags=["ops"])
    def health():
        return {"status": "ok"}

    admin_html = Path(__file__).parent / "admin_ui" / "index.html"

    @app.get("/admin-ui", include_in_schema=False)
    def admin_ui():
        return FileResponse(admin_html)

    return app


app = create_app()
