"""Redis access with an in-memory fallback so dev and tests need no infrastructure.

Redis is a cache / queue / pub-sub only; PostgreSQL stays the system of record.
"""
from __future__ import annotations

import json
import math
import time
from collections import defaultdict, deque
from functools import lru_cache
from typing import Any, Protocol

from app.core.config import get_settings
from app.utils.geo import Point, haversine_km


class CacheBackend(Protocol):
    def get_json(self, key: str) -> Any: ...
    def set_json(self, key: str, value: Any, ttl: int | None = None) -> None: ...
    def delete(self, key: str) -> None: ...
    def incr_window(self, key: str, ttl: int) -> int: ...
    def push(self, queue: str, item: dict) -> None: ...
    def pop(self, queue: str) -> dict | None: ...
    def geo_add(self, key: str, member: str, lat: float, lng: float) -> None: ...
    def geo_remove(self, key: str, member: str) -> None: ...
    def geo_radius(self, key: str, lat: float, lng: float, radius_km: float) -> list[str]: ...


class InMemoryCache:
    def __init__(self) -> None:
        self._kv: dict[str, tuple[Any, float | None]] = {}
        self._queues: dict[str, deque] = defaultdict(deque)
        self._geo: dict[str, dict[str, Point]] = defaultdict(dict)

    def _alive(self, key: str) -> bool:
        item = self._kv.get(key)
        if item is None:
            return False
        if item[1] is not None and item[1] < time.time():
            del self._kv[key]
            return False
        return True

    def get_json(self, key):
        return self._kv[key][0] if self._alive(key) else None

    def set_json(self, key, value, ttl=None):
        self._kv[key] = (value, time.time() + ttl if ttl else None)

    def delete(self, key):
        self._kv.pop(key, None)

    def incr_window(self, key, ttl):
        n = (self.get_json(key) or 0) + 1
        exp = self._kv[key][1] if self._alive(key) else time.time() + ttl
        self._kv[key] = (n, exp)
        return n

    def push(self, queue, item):
        self._queues[queue].append(item)

    def pop(self, queue):
        return self._queues[queue].popleft() if self._queues[queue] else None

    def geo_add(self, key, member, lat, lng):
        self._geo[key][member] = Point(lat, lng)

    def geo_remove(self, key, member):
        self._geo[key].pop(member, None)

    def geo_radius(self, key, lat, lng, radius_km):
        c = Point(lat, lng)
        return [m for m, p in self._geo[key].items() if haversine_km(c, p) <= radius_km]


class RedisCache:
    def __init__(self, url: str) -> None:
        import redis

        self.r = redis.Redis.from_url(url, decode_responses=True)

    def get_json(self, key):
        v = self.r.get(key)
        return json.loads(v) if v is not None else None

    def set_json(self, key, value, ttl=None):
        self.r.set(key, json.dumps(value), ex=ttl)

    def delete(self, key):
        self.r.delete(key)

    def incr_window(self, key, ttl):
        pipe = self.r.pipeline()
        pipe.incr(key)
        pipe.expire(key, ttl, nx=True)
        return int(pipe.execute()[0])

    def push(self, queue, item):
        self.r.rpush(queue, json.dumps(item))

    def pop(self, queue):
        v = self.r.lpop(queue)
        return json.loads(v) if v else None

    def geo_add(self, key, member, lat, lng):
        self.r.geoadd(key, (lng, lat, member))

    def geo_remove(self, key, member):
        self.r.zrem(key, member)

    def geo_radius(self, key, lat, lng, radius_km):
        return list(self.r.geosearch(key, longitude=lng, latitude=lat, radius=radius_km, unit="km"))


@lru_cache(maxsize=1)
def get_cache() -> CacheBackend:
    url = get_settings().redis_url
    return RedisCache(url) if url else InMemoryCache()
