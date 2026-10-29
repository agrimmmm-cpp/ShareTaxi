"""In-process WebSocket rooms. For multi-instance deployments swap ``broadcast`` for Redis pub/sub."""
from __future__ import annotations

from collections import defaultdict

import anyio
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self.rooms: dict[str, set[WebSocket]] = defaultdict(set)

    async def join(self, room: str, ws: WebSocket) -> None:
        self.rooms[room].add(ws)

    def leave(self, room: str, ws: WebSocket) -> None:
        self.rooms[room].discard(ws)

    async def broadcast(self, room: str, payload: dict) -> None:
        for ws in list(self.rooms.get(room, ())):
            try:
                await ws.send_json(payload)
            except Exception:
                self.leave(room, ws)

    def broadcast_from_sync(self, room: str, payload: dict) -> None:
        """Called from sync endpoints (thread-pool). Silently skipped when no event loop is reachable."""
        if not self.rooms.get(room):
            return
        try:
            anyio.from_thread.run(self.broadcast, room, payload)
        except Exception:
            pass


manager = ConnectionManager()
