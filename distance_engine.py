import math
from typing import Tuple


class DistanceEngine:
    """Provides geographic distance utilities using the Haversine formula."""

    EARTH_RADIUS_KM = 6371.0

    @staticmethod
    def haversine(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
        """
        Compute great-circle distance between two (lat, lon) pairs in kilometers.
        """
        lat1, lon1 = coord1
        lat2, lon2 = coord2

        # convert decimal degrees to radians
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        d_phi = math.radians(lat2 - lat1)
        d_lambda = math.radians(lon2 - lon1)

        a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return DistanceEngine.EARTH_RADIUS_KM * c

