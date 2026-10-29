from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "100000")

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core import cache as cache_mod
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.services import payment_service


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    s = Session()
    yield s
    s.close()


@pytest.fixture()
def client(db_session, monkeypatch):
    monkeypatch.setattr("app.main.engine", db_session.get_bind())
    monkeypatch.setattr("app.main.SessionLocal", lambda: _Ctx(db_session))
    cache_mod.get_cache.cache_clear()
    payment_service.set_gateway(None)
    app = create_app()

    def _db():
        db_session.expire_all()  # emulate one fresh session per request
        yield db_session

    app.dependency_overrides[get_db] = _db
    with TestClient(app) as c:
        yield c


class _Ctx:
    def __init__(self, s):
        self.s = s

    def __enter__(self):
        return self.s

    def __exit__(self, *a):
        return False


def auth_headers(client, email: str, password: str = "password123", name: str = "Test User") -> dict:
    r = client.post("/auth/register", json={"email": email, "password": password, "full_name": name})
    if r.status_code == 409:
        r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code in (200, 201), r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def tomorrow_iso(hour: int, minute: int = 0) -> str:
    t = (datetime.utcnow() + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return t.isoformat() + "Z"
