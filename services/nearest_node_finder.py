from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

from distance_engine import DistanceEngine


@dataclass(frozen=True)
class NearbyNode:
    location: str
    mode: str
    distance_km: float


class NearestNodeFinder:
    def __init__(self, coord_map: Dict[str, Tuple[float, float]]) -> None:
        self.coord_map = coord_map
        self.distance_engine = DistanceEngine()

    def find_nearest(
        self,
        *,
        lat: float,
        lon: float,
        graph_nodes: Iterable[Tuple[str, str]],
        allowed_modes: set[str],
        top_n: int = 5,
    ) -> List[NearbyNode]:
        out: List[NearbyNode] = []
        for (loc, mode) in graph_nodes:
            if mode not in allowed_modes:
                continue
            coord = self.coord_map.get(loc)
            if coord is None:
                continue
            d = self.distance_engine.haversine((lat, lon), coord)
            out.append(NearbyNode(location=loc, mode=mode, distance_km=d))
        out.sort(key=lambda x: x.distance_km)
        return out[: max(1, int(top_n))]

