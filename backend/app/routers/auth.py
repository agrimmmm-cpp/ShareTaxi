from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.ratelimit import rate_limit
from app.db.session import get_db
from app.models import Profile, User
from app.schemas.auth import LoginIn, MeOut, OAuthIn, ProfileUpdate, RefreshIn, RegisterIn, TokenPair
from app.services import auth_service, verification_service

router = APIRouter(prefix="/auth", tags=["auth"])
auth_limit = Depends(rate_limit("auth", 20))


def me_out(user: User) -> MeOut:
    p: Profile = user.profile
    return MeOut(
        id=user.id, email=user.email, full_name=p.full_name, phone=p.phone, roles=user.roles, email_verified=user.email_verified,
        phone_verified=user.phone_verified, identity_verified=p.identity_verified, rating_avg=p.rating_avg,
        rating_count=p.rating_count, driver_status=user.driver.verification_status if user.driver else None, push_token=p.push_token,
    )


def _wrap(fn, *a):
    try:
        return fn(*a)
    except auth_service.AuthError as exc:
        raise HTTPException(exc.status, str(exc))


@router.post("/register", response_model=TokenPair, status_code=201, dependencies=[auth_limit])
def register(data: RegisterIn, db: Session = Depends(get_db)):
    user = _wrap(auth_service.register, db, data)
    tokens = auth_service.issue_tokens(db, user)
    db.commit()
    return tokens


@router.post("/login", response_model=TokenPair, dependencies=[auth_limit])
def login(data: LoginIn, db: Session = Depends(get_db)):
    _, tokens = _wrap(auth_service.login, db, data.email, data.password)
    db.commit()
    return tokens


@router.post("/refresh", response_model=TokenPair, dependencies=[auth_limit])
def refresh(data: RefreshIn, db: Session = Depends(get_db)):
    tokens = _wrap(auth_service.refresh, db, data.refresh_token)
    db.commit()
    return tokens


@router.post("/oauth", response_model=TokenPair, dependencies=[auth_limit])
def oauth(data: OAuthIn, db: Session = Depends(get_db)):
    _, tokens = _wrap(auth_service.oauth_login, db, data.provider, data.id_token)
    db.commit()
    return tokens


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)):
    return me_out(user)


@router.patch("/me", response_model=MeOut)
def update_me(data: ProfileUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(user.profile, k, v)
    db.commit()
    return me_out(user)


@router.post("/verify-phone/start")
def start_phone(user: User = Depends(get_current_user)):
    verification_service.start_phone_verification(user.id)
    return {"sent": True}


@router.post("/verify-phone/confirm")
def confirm_phone(body: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verification_service.confirm_phone(db, user, str(body.get("code", ""))):
        raise HTTPException(400, "Invalid code")
    db.commit()
    return {"phone_verified": True}
