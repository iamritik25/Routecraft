from dataclasses import dataclass
from typing import Dict


@dataclass
class WeatherModel:
    """
    Encapsulates weather-based time multipliers per mode.
    """

    # Table from the specification.
    _TABLE: Dict[str, Dict[str, float]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self._TABLE is None:
            self._TABLE = {
                "clear": {
                    "walk": 1.0,
                    "metro": 1.0,
                    "bus": 1.0,
                    "auto": 1.0,
                    "cab": 1.0,
                },
                "light rain": {
                    "walk": 1.15,
                    "metro": 1.02,
                    "bus": 1.1,
                    "auto": 1.15,
                    "cab": 1.12,
                },
                "rain": {
                    "walk": 1.3,
                    "metro": 1.05,
                    "bus": 1.2,
                    "auto": 1.25,
                    "cab": 1.22,
                },
                "heavy rain": {
                    "walk": 1.5,
                    "metro": 1.08,
                    "bus": 1.35,
                    "auto": 1.4,
                    "cab": 1.35,
                },
            }

    def get_multiplier(self, condition: str, mode: str = "") -> float:
        """
        Returns the weather multiplier for a given condition and mode.
        """
        cond = (condition or "").strip().lower()
        m = (mode or "").strip().lower()
        table = self._TABLE or {}
        mode_row = table.get(cond)
        if not mode_row:
            return 1.0
        return mode_row.get(m, 1.0)


# Functional API requested in the spec.
_GLOBAL_MODEL = WeatherModel()


def get_weather_multiplier(weather: str, mode: str) -> float:
    """
    Public helper for computing weather multiplier per edge.
    """
    return _GLOBAL_MODEL.get_multiplier(weather, mode)

