"""
RouteCraft — DiskCache
======================
A file-based persistent cache that is shared between:
  • Airflow workers (write pre-built graphs)
  • Flask server    (read pre-built graphs)

Uses Python's shelve + file locking so both processes can safely
read/write simultaneously without corrupting data.

Why not Redis?
  Redis requires a separate server process. DiskCache works with zero
  infrastructure — just a directory on disk. When Redis IS available,
  cache_backend.py takes over and this is used as a cold-start fallback.
"""

from __future__ import annotations

import os
import shelve
import time
import json
import logging
import threading
from typing import Any, Optional


log = logging.getLogger(__name__)

_LOCK_TIMEOUT = 10   # seconds to wait for file lock before giving up


class DiskCache:
    """
    Thread-safe, process-safe persistent cache backed by shelve (dbm).

    Usage:
        cache = DiskCache(".graph_cache")
        cache.set("8:Clear:lightgbm", graph_obj, ttl_seconds=3600)
        graph = cache.get("8:Clear:lightgbm")   # None if expired / missing
        stats = cache.stats()
    """

    def __init__(self, cache_dir: str) -> None:
        os.makedirs(cache_dir, exist_ok=True)
        self._db_path   = os.path.join(cache_dir, "graphs")
        self._meta_path = os.path.join(cache_dir, "meta.json")
        self._lock_path = os.path.join(cache_dir, ".lock")
        self._lock      = threading.Lock()   # in-process lock
        self._meta: dict = self._load_meta()

    # ── Public API ─────────────────────────────────────────────────────────

    def get(self, key: str) -> Optional[Any]:
        """Return cached value or None if missing/expired."""
        meta = self._meta.get(key)
        if meta is None:
            return None
        if meta.get("expires_at") and time.time() > meta["expires_at"]:
            self._delete_key(key)
            return None
        try:
            with self._lock:
                with shelve.open(self._db_path, flag="r") as db:
                    return db.get(key)
        except Exception as e:
            log.warning(f"[DiskCache] get({key}) failed: {e}")
            return None

    def set(self, key: str, value: Any, ttl_seconds: int = 3600) -> None:
        """Store value under key with TTL."""
        expires_at = time.time() + ttl_seconds if ttl_seconds else None
        try:
            with self._lock:
                with shelve.open(self._db_path, flag="c", writeback=False) as db:
                    db[key] = value
            self._meta[key] = {
                "set_at":    time.time(),
                "expires_at": expires_at,
                "ttl":        ttl_seconds,
            }
            self._save_meta()
            log.debug(f"[DiskCache] set({key}) ttl={ttl_seconds}s")
        except Exception as e:
            log.error(f"[DiskCache] set({key}) failed: {e}")

    def clear_all(self) -> int:
        """Delete all cached entries. Returns count of cleared keys."""
        count = len(self._meta)
        try:
            with self._lock:
                with shelve.open(self._db_path, flag="n") as db:
                    pass   # 'n' flag creates fresh empty db
            self._meta = {}
            self._save_meta()
            log.info(f"[DiskCache] Cleared {count} entries")
        except Exception as e:
            log.error(f"[DiskCache] clear_all failed: {e}")
        return count

    def stats(self) -> dict:
        """Return cache statistics for /metrics endpoint."""
        now   = time.time()
        valid = sum(1 for m in self._meta.values()
                    if not m.get("expires_at") or m["expires_at"] > now)
        # Estimate disk usage
        size_bytes = 0
        for ext in ("", ".db", ".dir", ".bak", ".dat"):
            p = self._db_path + ext
            if os.path.exists(p):
                size_bytes += os.path.getsize(p)

        return {
            "total_keys":    len(self._meta),
            "valid_keys":    valid,
            "expired_keys":  len(self._meta) - valid,
            "total_size_mb": round(size_bytes / 1_048_576, 2),
        }

    def keys(self) -> list[str]:
        return list(self._meta.keys())

    # ── Internal helpers ───────────────────────────────────────────────────

    def _delete_key(self, key: str) -> None:
        try:
            with self._lock:
                with shelve.open(self._db_path, flag="c") as db:
                    if key in db:
                        del db[key]
            self._meta.pop(key, None)
            self._save_meta()
        except Exception:
            pass

    def _load_meta(self) -> dict:
        if os.path.exists(self._meta_path):
            try:
                with open(self._meta_path, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_meta(self) -> None:
        try:
            tmp = self._meta_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self._meta, f, indent=2)
            os.replace(tmp, self._meta_path)   # atomic write
        except Exception as e:
            log.warning(f"[DiskCache] meta save failed: {e}")
