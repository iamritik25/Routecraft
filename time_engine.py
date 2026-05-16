from dataclasses import dataclass
from typing import Optional

from traffic_model import get_traffic_multiplier
from weather_model import get_weather_multiplier

# Speeds reused from graph_builder; kept here for pure time calculations.
TRANSPORT_SPEED_KMPH = {
    "walk": 5.0,
    "auto": 25.0,
    "cab": 35.0,
    "metro": 45.0,
    "bus": 18.0,
}


@dataclass
class SegmentTimeBreakdown:
    distance_km: float
    base_time_min: float
    traffic_multiplier: float
    weather_multiplier: float
    fixed_delay_min: float
    final_time_min: float


def _base_time_hours(distance_km: float, mode: str) -> float:
    speed = TRANSPORT_SPEED_KMPH.get(mode, 10.0)
    return distance_km / max(speed, 1e-3)


def calculate_segment_time(
    distance_km: float,
    mode: str,
    hour: int,
    weather: str,
    source: Optional[str],
    destination: Optional[str],
    road_type: Optional[str] = None,
    zone_type: Optional[str] = None,
    switch_delay_min: float = 0.0,
    base_time_min_override: Optional[float] = None,
) -> SegmentTimeBreakdown:
    """
    Calculate base time, delays, and final time for a single edge.

    Formula (per spec):
    base_time_hours = distance_km / speed_kmph
    final_time_hours = base_time_hours × traffic_multiplier × weather_multiplier + fixed_delay_hours

    If base_time_min_override is provided (e.g. GTFS adjacent-stop time),
    it is used instead of distance/speed for the base time.
    """
    mode_l = (mode or "").lower()
    hour_int = int(hour)

    if base_time_min_override is not None:
        base_hours = max(base_time_min_override, 0.0) / 60.0
    else:
        base_hours = _base_time_hours(distance_km, mode_l)

    # Multipliers
    traffic_mult = get_traffic_multiplier(hour_int, mode_l, source, destination, road_type, zone_type, weather=weather)
    weather_mult = get_weather_multiplier(weather, mode_l)

    # Optional fixed delays
    fixed_delay = float(switch_delay_min)
    # Rain boarding delays only when it is raining (any non-clear condition).
    weather_l = (weather or "").strip().lower()
    if weather_l in {"light rain", "rain", "heavy rain"}:
        if mode_l == "bus":
            fixed_delay += 2.0
        elif mode_l == "metro":
            fixed_delay += 1.0

    final_hours = base_hours * traffic_mult * weather_mult + fixed_delay / 60.0

    base_min = base_hours * 60.0
    final_min = final_hours * 60.0

    return SegmentTimeBreakdown(
        distance_km=distance_km,
        base_time_min=base_min,
        traffic_multiplier=traffic_mult,
        weather_multiplier=weather_mult,
        fixed_delay_min=fixed_delay,
        final_time_min=final_min,
    )


_COST_ENGINE = None  # Lazy singleton — avoids circular import at module load time


def calculate_segment_cost(distance_km: float, mode: str, traffic_mult: float, weather_mult: float) -> float:
    """
    Thin wrapper around CostEngine-style logic.
    Uses a module-level singleton to avoid recreating the engine on every edge.
    """
    global _COST_ENGINE
    if _COST_ENGINE is None:
        from cost_engine import CostEngine  # deferred to break circular import
        _COST_ENGINE = CostEngine()
    return _COST_ENGINE.cost(mode, distance_km, traffic_mult=traffic_mult, weather_mult=weather_mult)


