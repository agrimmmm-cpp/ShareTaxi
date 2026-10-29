from __future__ import annotations

from datetime import datetime, timezone


def to_naive_utc(dt: datetime) -> datetime:
    """Normalise client datetimes: aware -> UTC, naive is assumed to already be UTC."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt
