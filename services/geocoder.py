"""
Nominatim geocoder with retry, timeout, and persistent file-based cache.
Never make the same HTTP call twice. Never crash the app on a network timeout.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Tuple

from logger import get_logger

log = get_logger(__name__)

_CACHE_FILE = Path("data/geocode_cache.json")
_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_USER_AGENT = "RouteCraft/1.0 (bengaluru-transit-planner)"
_TIMEOUT = 3.0      # seconds per attempt
_MAX_RETRIES = 3


def _load_cache() -> dict:
    if _CACHE_FILE.exists():
        try:
            return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_cache(cache: dict) -> None:
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except Exception as exc:
        log.warning("Failed to persist geocode cache", extra={"error": str(exc)})


class NominatimGeocoder:
    """
    Free geocoder using Nominatim.
    - Results are cached in data/geocode_cache.json (survives restarts).
    - Each request retries up to _MAX_RETRIES times with backoff.
    - On all failures, returns None — never raises to the caller.
    """

    def __init__(self) -> None:
        self._cache: dict = _load_cache()

    def geocode(self, query: str) -> Optional[Tuple[float, float]]:
        q = query.strip()
        if not q:
            return None

        if q in self._cache:
            cached = self._cache[q]
            if cached is None:
                return None
            return tuple(cached)  # type: ignore[return-value]

        result = self._fetch_with_retry(q)
        self._cache[q] = list(result) if result else None
        _save_cache(self._cache)
        return result

    def _fetch_with_retry(self, query: str) -> Optional[Tuple[float, float]]:
        params = urllib.parse.urlencode({
            "q": f"{query}, Bengaluru, India",
            "format": "json",
            "limit": 1,
        })
        url = f"{_NOMINATIM_URL}?{params}"

        last_exc: Optional[Exception] = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
                with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                    data = json.loads(resp.read().decode())
                if data:
                    lat = float(data[0]["lat"])
                    lon = float(data[0]["lon"])
                    log.info("Geocoded", extra={"query": query, "lat": lat, "lon": lon})
                    return lat, lon
                log.warning("Geocoder returned no results", extra={"query": query})
                return None
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_exc = exc
                wait = 2 ** (attempt - 1)  # exponential backoff: 1s, 2s, 4s
                log.warning(
                    "Geocoder attempt failed",
                    extra={"query": query, "attempt": attempt, "retry_in_s": wait, "error": str(exc)},
                )
                import time; time.sleep(wait)
            except Exception as exc:
                log.error("Geocoder unexpected error", extra={"query": query, "error": str(exc)})
                return None

        log.error(
            "Geocoder failed after all retries",
            extra={"query": query, "attempts": _MAX_RETRIES, "last_error": str(last_exc)},
        )
        return None
