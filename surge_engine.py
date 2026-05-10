"""
Dynamic surge pricing engine — models demand/supply imbalance like Uber's pricing.
Surge is driven by: peak hours, known high-demand areas, and weather (drivers go offline).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class SurgePricingEngine:
    MAX_SURGE: float = 3.5
    MIN_SURGE: float = 1.0

    # Peak hour windows (hour inclusive on left, exclusive on right)
    MORNING_PEAK: tuple = (7, 10)
    EVENING_PEAK: tuple = (17, 21)

    # High-demand area substrings (matched case-insensitively)
    HIGH_DEMAND_AREAS = {
        "koramangala", "mg road", "m.g. road", "whitefield",
        "electronic city", "hebbal", "silk board", "indiranagar",
    }

    def _demand_score(self, hour: int, area: Optional[str]) -> float:
        score = 1.0
        h = max(0, min(23, int(hour)))
        if self.MORNING_PEAK[0] <= h < self.MORNING_PEAK[1]:
            score += 0.7
        elif self.EVENING_PEAK[0] <= h < self.EVENING_PEAK[1]:
            score += 0.9
        elif 6 <= h < 7 or 21 <= h < 22:
            score += 0.2

        if area:
            name_l = area.lower()
            if any(a in name_l for a in self.HIGH_DEMAND_AREAS):
                score += 0.3
        return score

    def _supply_score(self, weather: str) -> float:
        """Fewer drivers available in bad weather → lower supply → higher surge."""
        w = (weather or "Clear").lower()
        if "heavy rain" in w:
            return 0.45
        if "rain" in w:
            return 0.65
        if "fog" in w:
            return 0.75
        if "overcast" in w:
            return 0.90
        return 1.0

    def get_surge(
        self,
        hour: int,
        weather: str,
        area: Optional[str] = None,
    ) -> float:
        demand = self._demand_score(hour, area)
        supply = self._supply_score(weather)
        raw = demand / max(supply, 0.1)
        return round(min(max(raw, self.MIN_SURGE), self.MAX_SURGE), 2)

    @staticmethod
    def get_surge_label(surge: float) -> str:
        if surge >= 2.5:
            return "🔴 Very High Surge"
        if surge >= 1.8:
            return "🟠 High Surge"
        if surge >= 1.3:
            return "🟡 Moderate Surge"
        return "🟢 Normal Pricing"
