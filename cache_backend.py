"""
Cache backend with Redis as primary and an in-process dict as graceful fallback.
Drop-in replacement for the plain dict _graph_cache in app.py.
Redis gives: persistence across restarts, multi-worker sharing, TTL expiry.
"""
from __future__ import annotations

import pickle
import time
from typing import Any, Optional

from logger import get_logger

log = get_logger(__name__)

_GRAPH_CACHE_TTL = 3600  # 1 hour


class CacheBackend:
    """Unified cache: Redis → in-process dict fallback."""

    def __init__(self, ttl: int = _GRAPH_CACHE_TTL, prefix: str = "rc") -> None:
        self._ttl = ttl
        self._prefix = prefix
        self._redis = None
        self._local: dict = {}
        self._local_ts: dict = {}
        self._hit_count = 0
        self._miss_count = 0
        self._backend_name = "local"
        self._connect_redis()

    def _connect_redis(self) -> None:
        try:
            import redis  # type: ignore
            r = redis.Redis(host="localhost", port=6379, db=0, socket_connect_timeout=1)
            r.ping()
            self._redis = r
            self._backend_name = "redis"
            log.info("Cache backend connected to Redis")
        except Exception as exc:
            log.warning("Redis unavailable — using in-process dict cache", extra={"reason": str(exc)})

    def _key(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    def get(self, key: str) -> Optional[Any]:
        k = self._key(key)
        if self._redis:
            try:
                raw = self._redis.get(k)
                if raw is not None:
                    self._hit_count += 1
                    return pickle.loads(raw)
                self._miss_count += 1
                return None
            except Exception as exc:
                # BP-1: log Redis errors so they don't vanish silently
                log.warning("Redis get failed; falling through to local cache",
                            extra={"key": k, "error": str(exc)})
        entry = self._local.get(k)
        if entry is None:
            self._miss_count += 1
            return None
        if time.time() - self._local_ts.get(k, 0) > self._ttl:
            del self._local[k]
            self._local_ts.pop(k, None)
            self._miss_count += 1
            return None
        self._hit_count += 1
        return entry

    def set(self, key: str, value: Any) -> None:
        k = self._key(key)
        if self._redis:
            try:
                self._redis.setex(k, self._ttl, pickle.dumps(value))
                return
            except Exception:
                pass
        self._local[k] = value
        self._local_ts[k] = time.time()

    def invalidate(self, key: str) -> None:
        k = self._key(key)
        if self._redis:
            try:
                self._redis.delete(k)
            except Exception:
                pass
        self._local.pop(k, None)
        self._local_ts.pop(k, None)

    def clear(self) -> None:
        if self._redis:
            try:
                self._redis.flushdb()
            except Exception:
                pass
        self._local.clear()
        self._local_ts.clear()

    @property
    def size(self) -> int:
        if self._redis:
            try:
                return self._redis.dbsize()
            except Exception:
                pass
        return len(self._local)

    @property
    def hit_count(self) -> int:
        return self._hit_count

    @property
    def miss_count(self) -> int:
        return self._miss_count

    @property
    def backend_name(self) -> str:
        return self._backend_name


# Singleton used by app.py
_graph_cache = CacheBackend(ttl=_GRAPH_CACHE_TTL, prefix="graph")


def get_graph_cache() -> CacheBackend:
    return _graph_cache
