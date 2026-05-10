from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from distance_engine import DistanceEngine
from gtfs_engine import normalize_station_name
from services.metro_parser import MetroStation, load_metro_stations, build_station_lookup


METRO_SPEED_KMPH = 35.0


@dataclass(frozen=True)
class MetroEdgeSpec:
    src: str
    dst: str
    line: str


def _minutes_for_distance(distance_km: float) -> float:
    hours = distance_km / max(METRO_SPEED_KMPH, 1e-3)
    return hours * 60.0


def build_metro_edges_from_lines(
    *,
    station_lookup: Dict[str, MetroStation],
    line_sequences: Dict[str, List[str]],
) -> List[MetroEdgeSpec]:
    """
    Build bidirectional edge specs between consecutive stations in each line.
    Station names are matched by normalized name against the dataset.
    """
    edges: List[MetroEdgeSpec] = []

    for line_name, seq in line_sequences.items():
        for i in range(len(seq) - 1):
            a_raw = seq[i]
            b_raw = seq[i + 1]
            a = station_lookup.get(normalize_station_name(a_raw))
            b = station_lookup.get(normalize_station_name(b_raw))
            if a is None or b is None:
                continue
            edges.append(MetroEdgeSpec(src=a.name, dst=b.name, line=line_name))
            edges.append(MetroEdgeSpec(src=b.name, dst=a.name, line=line_name))

    return edges


def integrate_metro_layer(
    *,
    coord_map: Dict[str, Tuple[float, float]],
    graph,
    hour: int,
    weather: str,
    line_sequences: Optional[Dict[str, List[str]]] = None,
    metro_dir: str = "data/metro",
) -> Tuple[Dict[str, Tuple[float, float]], int, int, set[str]]:
    """
    Add metro stations + metro edges into the existing multimodal graph.

    Returns:
      updated coord_map,
      added_station_count,
      added_edge_count,
      metro_station_names set
    """
    # Local import to avoid circular dependency at module import time.
    from graph_builder import Edge

    stations = load_metro_stations(metro_dir=metro_dir)
    if not stations:
        print("[METRO] No metro dataset found in data/metro.")
        return coord_map, 0, 0, set()

    lookup = build_station_lookup(stations)

    # Merge metro stations into coord_map and initialize nodes in graph.
    added_stations = 0
    metro_station_names: set[str] = set()
    for s in stations:
        name = s.name
        coord_map.setdefault(name, (s.lat, s.lon))
        metro_station_names.add(name)
        # ensure all mode nodes exist (graph builder uses fixed mode list)
        for mode in ["walk", "auto", "cab", "bus", "metro"]:
            graph.setdefault((name, mode), [])
        added_stations += 1

    # Default manual line orders (prototype)
    sequences = line_sequences or {
        "purple_line": [
            "Whitefield (Kadugodi)",
            "Hopefarm Channasandra",
            "KR Puram",
            "Baiyappanahalli",
            "Indiranagar",
            "Mahatma Gandhi Road",
            "Nadaprabhu Kempegowda Station, Majestic",
            "Vijayanagara",
            "Kengeri",
        ],
        "green_line": [
            "Nagasandra",
            "Yeshwanthpur",
            "Nadaprabhu Kempegowda Station, Majestic",
            "Lalbagh",
            "Jayanagar",
        ],
    }

    edge_specs = build_metro_edges_from_lines(station_lookup=lookup, line_sequences=sequences)
    de = DistanceEngine()

    added_edges = 0
    for spec in edge_specs:
        if spec.src not in coord_map or spec.dst not in coord_map:
            continue
        dist_km = de.haversine(coord_map[spec.src], coord_map[spec.dst])
        t_min = _minutes_for_distance(dist_km)
        desc = f"metro ({spec.line}) from {spec.src} to {spec.dst}"
        graph[(spec.src, "metro")].append(
            Edge(
                target=(spec.dst, "metro"),
                time_min=t_min,
                cost=0.0,  # metro fare can be added later; keep simple for now
                description=desc,
                distance_km=dist_km,
                base_time_min=t_min,
                traffic_multiplier=1.0,
                weather_multiplier=1.0,
                fixed_delay_min=0.0,
                final_time_min=t_min,
                mode="metro",
                route_source="metro_dataset",
                route_id=spec.line,
            )
        )
        added_edges += 1

    print(f"[METRO] Loaded stations={len(stations)}, integrated metro edges={added_edges}.")
    return coord_map, added_stations, added_edges, metro_station_names

