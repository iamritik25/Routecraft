"""
ETA confidence intervals — P10 / P50 / P90 bounds derived from edge-level
traffic multiplier variance, mirroring how Uber's ETA system produces a
time window rather than a single point estimate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np


@dataclass
class ETABounds:
    p10_min: float   # optimistic (10th percentile)
    p50_min: float   # median = total_time
    p90_min: float   # pessimistic (90th percentile)
    confidence: str  # "high" | "medium" | "low"
    spread_min: float


def compute_eta_bounds(
    total_time: float,
    traffic_multipliers: List[float],
    weather_multipliers: List[float],
) -> ETABounds:
    """
    Derive ETA bounds from the distribution of edge-level multipliers.

    High variance in multipliers (e.g. mix of uncongested + heavily congested
    segments) → wider window and lower confidence.
    Uniform multipliers → narrow window and high confidence.
    """
    if not traffic_multipliers or total_time <= 0:
        return ETABounds(
            p10_min=round(total_time * 0.85, 1),
            p50_min=round(total_time, 1),
            p90_min=round(total_time * 1.25, 1),
            confidence="low",
            spread_min=round(total_time * 0.40, 1),
        )

    tm = np.array(traffic_multipliers, dtype=float)
    wm = (
        np.array(weather_multipliers, dtype=float)
        if weather_multipliers
        else np.ones(len(tm))
    )

    combined = tm * wm
    mean_m = float(np.mean(combined))
    std_m = float(np.std(combined))
    cv = std_m / max(mean_m, 1e-6)  # coefficient of variation

    # P10 / P90 scaling based on CV
    p10 = total_time * max(0.65, 1.0 - cv * 1.8)
    p90 = total_time * (1.0 + cv * 2.2)

    if cv < 0.05:
        confidence = "high"
    elif cv < 0.15:
        confidence = "medium"
    else:
        confidence = "low"

    return ETABounds(
        p10_min=round(p10, 1),
        p50_min=round(total_time, 1),
        p90_min=round(p90, 1),
        confidence=confidence,
        spread_min=round(p90 - p10, 1),
    )
