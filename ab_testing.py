"""
A/B testing framework for ML backend selection.
Routes a configurable % of traffic to the PyTorch MPS model vs LightGBM.
Uses deterministic hashing for sticky sessions (same request ID → same model).
"""
from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from threading import Lock
from typing import Dict, Optional

BACKENDS = ("lightgbm", "mps_nn")
_DEFAULT_BACKEND = "lightgbm"

# Configurable via env var: set MPS_TRAFFIC_PERCENT=20 for 20% PyTorch traffic
_MPS_PERCENT = int(os.environ.get("MPS_TRAFFIC_PERCENT", "10"))

# Thread-safe counters for observability (exposed via /metrics)
_counts: Dict[str, int] = defaultdict(int)
_lock = Lock()


def get_model_backend(session_id: Optional[str] = None) -> str:
    """
    Returns 'lightgbm' or 'mps_nn' based on:
    1. TRAFFIC_MODEL_TYPE env var (hard override — used in training/prod switch)
    2. Deterministic hash of session_id (sticky sessions)
    3. Random bucket if no session_id
    """
    env_override = os.environ.get("TRAFFIC_MODEL_TYPE", "").lower().strip()
    if env_override in BACKENDS:
        _record(env_override)
        return env_override

    if session_id:
        bucket = int(hashlib.md5(session_id.encode()).hexdigest(), 16) % 100
    else:
        import random
        bucket = random.randint(0, 99)

    backend = "mps_nn" if bucket < _MPS_PERCENT else _DEFAULT_BACKEND
    _record(backend)
    return backend


def _record(backend: str) -> None:
    with _lock:
        _counts[backend] += 1


def get_backend_counts() -> Dict[str, int]:
    """Return a snapshot of how many requests each backend has served."""
    with _lock:
        return dict(_counts)


def reset_counts() -> None:
    with _lock:
        _counts.clear()
