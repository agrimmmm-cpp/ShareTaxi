"""Admin-editable settings persisted in the DB and applied to the in-process config.

(Single-instance semantics: with several API replicas, re-read from the DB on a timer or via Redis pub/sub.)"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import utcnow
from app.models import PlatformSetting

FEE_KEY = "platform_commission_rate"


def apply_from_db(db: Session) -> None:
    row = db.get(PlatformSetting, FEE_KEY)
    if row is not None:
        get_settings().pricing.platform_commission_rate = float(row.value["value"])


def set_commission(db: Session, rate: float) -> None:
    row = db.get(PlatformSetting, FEE_KEY)
    if row is None:
        db.add(PlatformSetting(key=FEE_KEY, value={"value": rate}, updated_at=utcnow()))
    else:
        row.value, row.updated_at = {"value": rate}, utcnow()
    get_settings().pricing.platform_commission_rate = rate
