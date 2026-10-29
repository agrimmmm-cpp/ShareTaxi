from __future__ import annotations

import uuid
from datetime import timedelta

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import log_event
from app.core.security import create_access_token, hash_password, hash_refresh_token, new_refresh_token, verify_password
from app.db.base import utcnow
from app.models import RefreshToken, User
from app.repositories.users import UserRepository
from app.schemas.auth import RegisterIn, TokenPair


class AuthError(Exception):
    def __init__(self, message: str, status: int = 401) -> None:
        super().__init__(message)
        self.status = status


def issue_tokens(db: Session, user: User, family_id: str | None = None) -> TokenPair:
    s = get_settings()
    raw, hashed = new_refresh_token()
    db.add(RefreshToken(user_id=user.id, token_hash=hashed, family_id=family_id or str(uuid.uuid4()),
                        expires_at=utcnow() + timedelta(days=s.refresh_token_days)))
    return TokenPair(access_token=create_access_token(user.id, user.roles), refresh_token=raw, expires_in=s.access_token_minutes * 60)


def register(db: Session, data: RegisterIn) -> User:
    repo = UserRepository(db)
    if repo.by_email(data.email):
        raise AuthError("An account with this email already exists", 409)
    user = repo.create(data.email, hash_password(data.password), data.full_name, data.phone)
    log_event("auth.registered", user_id=user.id)
    return user


def login(db: Session, email: str, password: str) -> tuple[User, TokenPair]:
    user = UserRepository(db).by_email(email)
    if user is None or not verify_password(password, user.password_hash):
        log_event("auth.login_failed", email=email)
        raise AuthError("Incorrect email or password")
    if user.is_suspended or not user.is_active:
        raise AuthError("Account suspended", 403)
    return user, issue_tokens(db, user)


def refresh(db: Session, raw_token: str) -> TokenPair:
    """Rotate: the presented token is revoked and a new one issued in the same family. Presenting an
    already-revoked token means theft: the whole family is revoked."""
    row = db.query(RefreshToken).filter(RefreshToken.token_hash == hash_refresh_token(raw_token)).first()
    if row is None:
        raise AuthError("Invalid refresh token")
    if row.revoked:
        db.query(RefreshToken).filter(RefreshToken.family_id == row.family_id).update({"revoked": True})
        db.commit()
        log_event("auth.refresh_reuse_detected", user_id=row.user_id, family=row.family_id)
        raise AuthError("Refresh token reuse detected; please sign in again")
    if row.expires_at < utcnow():
        raise AuthError("Refresh token expired")
    user = db.get(User, row.user_id)
    if user is None or user.is_suspended or not user.is_active:
        raise AuthError("Account unavailable", 403)
    row.revoked = True
    return issue_tokens(db, user, row.family_id)


def oauth_login(db: Session, provider: str, id_token: str) -> tuple[User, TokenPair]:
    """Google id_token verification via Google's tokeninfo endpoint. Apple needs JWKS verification (add
    ``apple_client_id`` + PyJWT's PyJWKClient); left as an explicit extension point."""
    s = get_settings()
    if provider != "google" or not s.google_client_id:
        raise AuthError(f"{provider} sign-in is not configured", 501)
    resp = httpx.get("https://oauth2.googleapis.com/tokeninfo", params={"id_token": id_token}, timeout=8)
    info = resp.json()
    if resp.status_code != 200 or info.get("aud") != s.google_client_id or info.get("email_verified") not in ("true", True):
        raise AuthError("Invalid Google token")
    repo = UserRepository(db)
    user = repo.by_email(info["email"]) or repo.create(
        info["email"], None, info.get("name") or info["email"].split("@")[0], oauth_provider="google", oauth_subject=info["sub"], email_verified=True
    )
    return user, issue_tokens(db, user)
