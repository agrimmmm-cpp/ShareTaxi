from __future__ import annotations

from fastapi import HTTPException, Request

from app.core.cache import get_cache
from app.core.config import get_settings


def rate_limit(scope: str, per_minute: int | None = None):
    """FastAPI dependency: fixed-window limiter keyed by client IP + scope, backed by Redis."""

    def dep(request: Request) -> None:
        limit = per_minute or get_settings().rate_limit_per_minute
        ip = request.client.host if request.client else "unknown"
        n = get_cache().incr_window(f"rl:{scope}:{ip}", 60)
        if n > limit:
            raise HTTPException(status_code=429, detail="Too many requests", headers={"Retry-After": "60"})

    return dep
