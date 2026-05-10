from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from config import MODE_SWITCH_COST, MODE_SWITCH_TIME_MIN
from cost_engine import CostEngine
from distance_engine import DistanceEngine
from graph_builder import Edge


State = Tuple[str, str]  # (location, mode)
Graph = Dict[State, List[Edge]]


@dataclass(frozen=True)
class LastMileRule:
    max_walk_km: float = 0.5
    max_auto_km: float = 2.0
    walk_speed_kmph: float = 5.0
    auto_speed_kmph: float = 25.0
    allow_cab_beyond_km: float = 2.0


class LastMileBuilder:
    def __init__(self, coord_map: Dict[str, Tuple[float, float]]) -> None:
        self.coord_map = coord_map
        self.distance_engine = DistanceEngine()
        self.cost_engine = CostEngine()

    def _time_min(self, distance_km: float, speed_kmph: float) -> float:
        return (distance_km / max(speed_kmph, 1e-3)) * 60.0

    def ensure_virtual_place_nodes(self, graph: Graph, place_name: str) -> None:
        """
        Add minimal virtual nodes + local switch edges (walk/auto/cab only).
        """
        modes = ["walk", "auto", "cab"]
        for m in modes:
            graph.setdefault((place_name, m), [])

        for from_m in modes:
            for to_m in modes:
                if from_m == to_m:
                    continue
                graph[(place_name, from_m)].append(
                    Edge(
                        target=(place_name, to_m),
                        time_min=MODE_SWITCH_TIME_MIN,
                        cost=MODE_SWITCH_COST,
                        description=f"switch from {from_m} to {to_m} at {place_name}",
                        distance_km=0.0,
                        base_time_min=0.0,
                        traffic_multiplier=1.0,
                        weather_multiplier=1.0,
                        fixed_delay_min=MODE_SWITCH_TIME_MIN,
                        final_time_min=MODE_SWITCH_TIME_MIN,
                        mode=to_m,
                        route_source="virtual",
                    )
                )

    def connect_place_to_transport(
        self,
        graph: Graph,
        *,
        place_name: str,
        place_coord: Tuple[float, float],
        transport_locs: List[str],
        rule: LastMileRule | None = None,
    ) -> None:
        """
        Add temporary last-mile edges between a place and nearby transport locations.
        Adds both directions so place can be source or destination.
        """
        r = rule or LastMileRule()
        self.ensure_virtual_place_nodes(graph, place_name)

        for loc in transport_locs:
            coord = self.coord_map.get(loc)
            if coord is None:
                continue
            d = self.distance_engine.haversine(place_coord, coord)
            if d <= 0:
                continue

            if d <= r.max_walk_km:
                t = self._time_min(d, r.walk_speed_kmph)
                cost = 0.0
                desc = f"walk from {place_name} to {loc}"
                desc_back = f"walk from {loc} to {place_name}"
                graph[(place_name, "walk")].append(
                    Edge(
                        target=(loc, "walk"),
                        time_min=t,
                        cost=cost,
                        description=desc,
                        distance_km=d,
                        base_time_min=t,
                        traffic_multiplier=1.0,
                        weather_multiplier=1.0,
                        fixed_delay_min=0.0,
                        final_time_min=t,
                        mode="walk",
                        route_source="last_mile",
                    )
                )
                graph[(loc, "walk")].append(
                    Edge(
                        target=(place_name, "walk"),
                        time_min=t,
                        cost=cost,
                        description=desc_back,
                        distance_km=d,
                        base_time_min=t,
                        traffic_multiplier=1.0,
                        weather_multiplier=1.0,
                        fixed_delay_min=0.0,
                        final_time_min=t,
                        mode="walk",
                        route_source="last_mile",
                    )
                )

            # Auto for mid range, cab as fallback for longer.
            if d <= r.max_auto_km:
                mode = "auto"
                speed = r.auto_speed_kmph
            elif d > r.allow_cab_beyond_km:
                mode = "cab"
                speed = 35.0
            else:
                mode = "auto"
                speed = r.auto_speed_kmph

            t2 = self._time_min(d, speed)
            cost2 = self.cost_engine.cost(mode, d, traffic_mult=1.0, weather_mult=1.0)
            desc2 = f"{mode} from {place_name} to {loc}"
            desc2_back = f"{mode} from {loc} to {place_name}"
            graph[(place_name, mode)].append(
                Edge(
                    target=(loc, mode),
                    time_min=t2,
                    cost=cost2,
                    description=desc2,
                    distance_km=d,
                    base_time_min=t2,
                    traffic_multiplier=1.0,
                    weather_multiplier=1.0,
                    fixed_delay_min=0.0,
                    final_time_min=t2,
                    mode=mode,
                    route_source="last_mile",
                )
            )
            graph[(loc, mode)].append(
                Edge(
                    target=(place_name, mode),
                    time_min=t2,
                    cost=cost2,
                    description=desc2_back,
                    distance_km=d,
                    base_time_min=t2,
                    traffic_multiplier=1.0,
                    weather_multiplier=1.0,
                    fixed_delay_min=0.0,
                    final_time_min=t2,
                    mode=mode,
                    route_source="last_mile",
                )
            )

