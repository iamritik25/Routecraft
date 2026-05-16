"""
Traffic model with two-layer design:

  Layer 1 (ML): Travel Time Index per (area, weather, day_of_week) predicted
                by a LightGBM or PyTorch-MPS model trained on the Bangalore
                Traffic Pulse dataset.
  Layer 2 (heuristic): Hour-of-day curve + mode sensitivity + weather.

If the ML model is unavailable or the source/destination falls outside the
trained areas, the model gracefully falls back to the original heuristic.

A module-level flag `LAST_PREDICTION_USED_ML` is updated after every call so
the API layer can surface an "ML-predicted" badge to the UI.
"""

import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

# Counters updated on every multiplier call so the API layer can surface
# how many segments in a request were served by the ML model vs. heuristic.
ML_HIT_COUNT: int = 0
HEURISTIC_COUNT: int = 0
LAST_ML_BACKEND: Optional[str] = None
LAST_ML_AREAS: list = []
_ml_lock = threading.Lock()  # guards all four counters above


def _touch_ml_state(area: Optional[str], backend: Optional[str]) -> None:
    global ML_HIT_COUNT, HEURISTIC_COUNT, LAST_ML_BACKEND, LAST_ML_AREAS
    with _ml_lock:
        if area is not None:
            ML_HIT_COUNT += 1
            LAST_ML_BACKEND = backend
            if area not in LAST_ML_AREAS:
                LAST_ML_AREAS.append(area)
        else:
            HEURISTIC_COUNT += 1


def reset_ml_state() -> None:
    global ML_HIT_COUNT, HEURISTIC_COUNT, LAST_ML_BACKEND, LAST_ML_AREAS
    with _ml_lock:
        ML_HIT_COUNT = 0
        HEURISTIC_COUNT = 0
        LAST_ML_BACKEND = None
        LAST_ML_AREAS = []


def ml_summary() -> dict:
    """Thread-safe snapshot of the current ML usage counters for API responses."""
    with _ml_lock:
        return {
            "used": ML_HIT_COUNT > 0,
            "hits": ML_HIT_COUNT,
            "heuristic_hits": HEURISTIC_COUNT,
            "backend": LAST_ML_BACKEND,
            "areas": list(LAST_ML_AREAS),
        }


@dataclass
class TrafficModel:
    """
    Time-of-day and mode-aware traffic model.
    """

    def base_time_of_day_multiplier(self, hour: int) -> float:
        hour = max(0, min(23, int(hour)))
        if 6 <= hour < 8:
            return 1.1
        if 8 <= hour < 11:
            return 1.5
        if 11 <= hour < 16:
            return 1.2
        if 16 <= hour < 19:
            return 1.8
        if 19 <= hour < 22:
            return 1.3
        return 1.0

    def mode_sensitivity(self, mode: str) -> float:
        m = (mode or "").lower()
        if m == "walk":
            return 0.0
        if m == "metro":
            return 0.05
        if m == "bus":
            return 0.25
        if m == "auto":
            return 0.20
        if m == "cab":
            return 0.25
        return 0.0

    def zone_penalty(
        self,
        hour: int,
        source: Optional[str],
        destination: Optional[str],
        road_type: Optional[str] = None,
        zone_type: Optional[str] = None,
    ) -> float:
        """
        Extra penalties used only as a fallback when the ML model does not
        produce a prediction for this segment.
        """
        hour = max(0, min(23, int(hour)))
        names = f"{source or ''} {destination or ''}".lower()
        penalty = 0.0

        hotspots = [
            "mg road", "majestic", "silk board",
            "whitefield", "electronic city", "hebbal",
        ]
        if any(h in names for h in hotspots):
            if 8 <= hour < 11 or 16 <= hour < 20:
                penalty += 0.25
            elif 6 <= hour < 8 or 11 <= hour < 16 or 19 <= hour < 22:
                penalty += 0.15
            else:
                penalty += 0.10

        if road_type:
            rt = road_type.lower()
            if "arterial" in rt:
                penalty += 0.1
            elif "highway" in rt:
                penalty += 0.15
        if zone_type:
            zt = zone_type.lower()
            if "central" in zt or "business" in zt:
                penalty += 0.15

        return penalty

    def _ml_zone_factor(
        self,
        source: Optional[str],
        destination: Optional[str],
        weather: Optional[str],
    ) -> Optional[tuple]:
        """
        Query the trained model for a (TTI, area, backend) triple.
        Returns None if the model is absent or the area is unknown.
        """
        try:
            from services.traffic_ml import get_predictor
        except Exception:
            return None

        predictor = get_predictor()
        if not predictor.available:
            return None

        now = datetime.now()
        result = predictor.multiplier_for_segment(
            hour=0,  # hour is handled by the heuristic layer
            source=source,
            destination=destination,
            weather=weather or "Clear",
            day_of_week=now.weekday(),
            month=now.month,
        )
        if result is None:
            return None
        tti, area = result
        return tti, area, predictor.backend

    def get_multiplier(
        self,
        hour: int,
        mode: str = "",
        source: Optional[str] = None,
        destination: Optional[str] = None,
        road_type: Optional[str] = None,
        zone_type: Optional[str] = None,
        weather: Optional[str] = None,
    ) -> float:
        """
        Compute the final traffic multiplier for a segment.

        Walking edges ignore traffic entirely.
        For all other modes:
          base = hour curve
          zone_bonus = (ml_tti - 1.0) if ML available, else heuristic zone penalty
          effective = base + (base-1) * mode_sensitivity + zone_bonus
        """
        base = self.base_time_of_day_multiplier(hour)

        if (mode or "").lower() == "walk":
            _touch_ml_state(None, None)
            return 1.0

        sensitivity = self.mode_sensitivity(mode)

        ml_result = self._ml_zone_factor(source, destination, weather)
        if ml_result is not None:
            tti, area, backend = ml_result
            # ML TTI lives in the 1.0-1.5 range; the zone bonus is (TTI - 1).
            zone_bonus = max(0.0, tti - 1.0)
            _touch_ml_state(area, backend)
        else:
            zone_bonus = self.zone_penalty(hour, source, destination, road_type, zone_type)
            _touch_ml_state(None, None)

        effective = base + (base - 1.0) * sensitivity + zone_bonus
        return max(1.0, effective)


_GLOBAL_MODEL = TrafficModel()


def get_traffic_multiplier(
    hour: int,
    mode: str,
    source: Optional[str],
    destination: Optional[str],
    road_type: Optional[str] = None,
    zone_type: Optional[str] = None,
    weather: Optional[str] = None,
) -> float:
    """
    Public helper used by the time engine and graph builder.
    Accepts an optional `weather` kwarg so the ML layer can condition on it.
    """
    return _GLOBAL_MODEL.get_multiplier(
        hour=hour,
        mode=mode,
        source=source,
        destination=destination,
        road_type=road_type,
        zone_type=zone_type,
        weather=weather,
    )
