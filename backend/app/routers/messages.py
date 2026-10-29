from __future__ import annotations

import re

import jwt
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.security import decode_access_token
from app.core.ws import manager
from app.db.session import SessionLocal, get_db
from app.models import Message, Profile, Ride, RideStatus, User
from app.schemas.misc import MessageIn, MessageOut

router = APIRouter(tags=["chat"])

QUICK_MESSAGES = [
    "I'm at the pickup point.", "Running 5 minutes late.", "Where should I meet you?",
    "I can see you, pulling up now.", "Thanks, see you soon!",
]
_PHONE = re.compile(r"(\+?\d[\d\s().-]{6,}\d)")


def sanitize(body: str) -> str:
    """Protect personal phone numbers: chat is the only contact channel, so numbers are masked."""
    return _PHONE.sub("[number hidden]", body)


def _participant(db: Session, ride_id: int, user: User) -> Ride:
    ride = db.get(Ride, ride_id)
    if ride is None:
        raise HTTPException(404, "Ride not found")
    is_pax = any(p.user_id == user.id and p.status != "cancelled" for p in ride.passengers)
    is_driver = user.driver is not None and ride.driver_id == user.driver.id
    if not (is_pax or is_driver):
        raise HTTPException(404, "Ride not found")
    return ride


def _label(db: Session, ride: Ride, sender_id: int) -> str:
    name = db.query(Profile).filter(Profile.user_id == sender_id).one().full_name.split()[0]
    return f"{name} (driver)" if ride.driver.user_id == sender_id else name


def _out(db: Session, ride: Ride, m: Message, viewer_id: int) -> MessageOut:
    return MessageOut(id=m.id, ride_id=m.ride_id, sender_id=m.sender_id, sender_label=_label(db, ride, m.sender_id),
                      body=m.body, kind=m.kind, created_at=m.created_at, mine=m.sender_id == viewer_id)


@router.get("/messages/quick")
def quick_messages():
    return QUICK_MESSAGES


@router.get("/rides/{ride_id}/messages", response_model=list[MessageOut])
def list_messages(ride_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ride = _participant(db, ride_id, user)
    rows = db.query(Message).filter(Message.ride_id == ride_id).order_by(Message.id).limit(500).all()
    return [_out(db, ride, m, user.id) for m in rows]


@router.post("/rides/{ride_id}/messages", response_model=MessageOut, status_code=201)
def send_message(ride_id: int, data: MessageIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ride = _participant(db, ride_id, user)
    if ride.status == RideStatus.CANCELLED:
        raise HTTPException(409, "This ride was cancelled")
    m = Message(ride_id=ride_id, sender_id=user.id, body=sanitize(data.body), kind=data.kind)
    db.add(m)
    db.commit()
    out = _out(db, ride, m, user.id)
    manager.broadcast_from_sync(f"ride:{ride_id}", {"type": "message", **out.model_dump(mode="json", exclude={"mine"})})
    return out


@router.websocket("/ws/rides/{ride_id}")
async def ride_socket(ws: WebSocket, ride_id: int, token: str):
    """Live chat. Auth via ?token=<access token>; messages sent here are persisted exactly like REST posts."""
    try:
        user_id = int(decode_access_token(token)["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        await ws.close(code=4401)
        return
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        try:
            ride = _participant(db, ride_id, user)
        except HTTPException:
            await ws.close(code=4403)
            return
        await ws.accept()
        room = f"ride:{ride_id}"
        await manager.join(room, ws)
        try:
            while True:
                data = await ws.receive_json()
                body = str(data.get("body", "")).strip()[:1000]
                if not body:
                    continue
                m = Message(ride_id=ride_id, sender_id=user_id, body=sanitize(body), kind=data.get("kind", "text") if data.get("kind") in ("text", "quick") else "text")
                db.add(m)
                db.commit()
                out = _out(db, ride, m, user_id)
                await manager.broadcast(room, {"type": "message", **out.model_dump(mode="json", exclude={"mine"})})
        except WebSocketDisconnect:
            pass
        finally:
            manager.leave(room, ws)
    finally:
        db.close()


@router.websocket("/ws/me")
async def user_socket(ws: WebSocket, token: str):
    """Pushes in-app notifications (and ride state changes) to the signed-in user in real time."""
    try:
        user_id = int(decode_access_token(token)["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        await ws.close(code=4401)
        return
    await ws.accept()
    room = f"user:{user_id}"
    await manager.join(room, ws)
    try:
        while True:
            await ws.receive_text()  # keep-alive pings
    except WebSocketDisconnect:
        pass
    finally:
        manager.leave(room, ws)
