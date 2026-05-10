from dataclasses import dataclass


@dataclass
class CostEngine:
    """
    Computes monetary cost for different transport modes.
    """

    # Simple Bengaluru-ish model (not official pricing):
    # - Auto/cab have a base fare + per-km component
    # - Metro is distance-based and does not surge with traffic/rain
    BASE_FARE = {
        "walk": 0.0,
        "auto": 30.0,
        "cab": 50.0,
        "metro": 10.0,
        # BMTC government buses generally have low minimum fares.
        "bus": 10.0,
    }

    COST_PER_KM = {
        "walk": 0.0,
        "auto": 14.0,
        "cab": 18.0,
        "metro": 6.0,
        "bus": 3.0,
    }

    def _surge_multiplier(self, mode: str, traffic_mult: float, weather_mult: float) -> float:
        """
        Apply surge only for on-road modes. Keep it conservative so
        route selection doesn't become unstable.
        """
        # No surge for metro/bus/walk in this simplified model.
        if mode not in {"auto", "cab"}:
            return 1.0
        # Translate time multipliers into partial cost multipliers.
        # Example: traffic 1.8 -> +40% cost, heavy rain 1.6 -> +30% cost.
        traffic_component = 1.0 + max(0.0, traffic_mult - 1.0) * 0.5
        weather_component = 1.0 + max(0.0, weather_mult - 1.0) * 0.3
        return traffic_component * weather_component

    def cost(
        self,
        mode: str,
        distance_km: float,
        *,
        traffic_mult: float = 1.0,
        weather_mult: float = 1.0,
    ) -> float:
        base = self.BASE_FARE.get(mode, 0.0)
        rate = self.COST_PER_KM.get(mode, 0.0)
        surge = self._surge_multiplier(mode, traffic_mult, weather_mult)
        return (base + distance_km * rate) * surge


