import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from data_loader import DataLoader
from distance_engine import DistanceEngine
from config import GTFS_FOLDER, METRO_DEFAULT_SPEED_KMPH


@dataclass
class MetroStation:
    id: str
    name: str
    lat: float
    lon: float


@dataclass
class MetroEdge:
    source_name: str
    destination_name: str
    distance_km: float
    base_time_min: float
    route_id: Optional[str]
    trip_id: Optional[str]


def normalize_station_name(name: str) -> str:
    """
    Normalizes station/location names so that variants such as
    'Kengeri', 'Kengeri Metro Station' are treated as the same.
    """
    s = (name or "").strip().lower()
    # Remove common suffixes
    s = re.sub(r"\bmetro station\b", "", s)
    s = re.sub(r"\bstation\b", "", s)
    s = re.sub(r"\bttmc\b", "", s)
    s = re.sub(r"\b(bus station|bus stand)\b", "", s)
    s = re.sub(r"[\(\)]", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _parse_hhmmss(t: str) -> Optional[int]:
    """
    Parse GTFS HH:MM:SS into minutes from midnight.
    Supports 24+ hours for trips that run past midnight.
    """
    if not t:
        return None
    parts = t.split(":")
    if len(parts) != 3:
        return None
    try:
        h = int(parts[0])
        m = int(parts[1])
        s = int(parts[2])
    except ValueError:
        return None
    return h * 60 + m + s // 60


def build_metro_stations(base_dir: str = ".") -> Dict[str, MetroStation]:
    """
    Load GTFS stops and convert them into MetroStation objects.
    """
    loader = DataLoader(base_dir=base_dir)
    feed = loader.load_gtfs_data(GTFS_FOLDER)
    stops = feed.get("stops", [])

    stations: Dict[str, MetroStation] = {}
    duplicate_names: Dict[str, int] = {}

    for row in stops:
        stop_id = str(row.get("stop_id", "")).strip()
        name = str(row.get("stop_name", "")).strip()
        lat = row.get("stop_lat")
        lon = row.get("stop_lon")
        if not stop_id or not name or lat in (None, "") or lon in (None, ""):
            continue
        try:
            lat_f = float(lat)
            lon_f = float(lon)
        except ValueError:
            continue

        station = MetroStation(id=stop_id, name=name, lat=lat_f, lon=lon_f)
        stations[stop_id] = station

        key = normalize_station_name(name)
        duplicate_names[key] = duplicate_names.get(key, 0) + 1

    print(f"[GTFS] Loaded {len(stations)} metro stops from GTFS.")
    dup_count = sum(1 for _k, c in duplicate_names.items() if c > 1)
    if dup_count:
        print(f"[GTFS] Warning: {dup_count} normalized station names have duplicates.")

    return stations


def get_adjacent_station_edges(
    base_dir: str = ".",
) -> List[Tuple[str, str, float, float, Optional[str], Optional[str]]]:
    """
    Using routes, trips and stop_times, build adjacent station edges:
    (from_stop_id, to_stop_id, distance_km, base_time_min, route_id, trip_id)
    """
    loader = DataLoader(base_dir=base_dir)
    feed = loader.load_gtfs_data(GTFS_FOLDER)

    routes = feed.get("routes", [])
    trips = feed.get("trips", [])
    stop_times = feed.get("stop_times", [])

    if not routes or not trips or not stop_times:
        print("[GTFS] Missing one or more GTFS files, metro graph will fall back to synthetic data.")
        return []

    # Map route_id -> route_type
    route_type_by_id: Dict[str, str] = {}
    for r in routes:
        rid = str(r.get("route_id", "")).strip()
        if not rid:
            continue
        route_type_by_id[rid] = str(r.get("route_type", "")).strip()

    # Only consider metro-like routes (type 1 by GTFS spec).
    metro_route_ids = {rid for rid, t in route_type_by_id.items() if t == "1"}
    if not metro_route_ids:
        print("[GTFS] No routes with route_type=1 (metro) found.")
        return []

    # Map trip_id -> route_id (only metro trips)
    metro_trips: Dict[str, str] = {}
    for tr in trips:
        trip_id = str(tr.get("trip_id", "")).strip()
        route_id = str(tr.get("route_id", "")).strip()
        if not trip_id or not route_id or route_id not in metro_route_ids:
            continue
        metro_trips[trip_id] = route_id

    # Group stop_times by trip
    times_by_trip: Dict[str, List[Dict[str, str]]] = {}
    for row in stop_times:
        trip_id = str(row.get("trip_id", "")).strip()
        if trip_id not in metro_trips:
            continue
        times_by_trip.setdefault(trip_id, []).append(row)

    distance_engine = DistanceEngine()
    stations = build_metro_stations(base_dir=base_dir)

    edges: Dict[Tuple[str, str], Tuple[float, float, Optional[str], Optional[str]]] = {}

    for trip_id, rows in times_by_trip.items():
        route_id = metro_trips[trip_id]
        # Sort by stop_sequence
        try:
            ordered = sorted(rows, key=lambda r: int(r.get("stop_sequence", "0")))
        except ValueError:
            ordered = rows

        for i in range(len(ordered) - 1):
            a = ordered[i]
            b = ordered[i + 1]
            stop_a = str(a.get("stop_id", "")).strip()
            stop_b = str(b.get("stop_id", "")).strip()
            if stop_a not in stations or stop_b not in stations:
                continue
            sta = stations[stop_a]
            stb = stations[stop_b]

            # Time difference priority
            t_dep = _parse_hhmmss(a.get("departure_time", "") or a.get("arrival_time", ""))
            t_arr = _parse_hhmmss(b.get("arrival_time", "") or b.get("departure_time", ""))
            base_time_min: Optional[float] = None
            if t_dep is not None and t_arr is not None and t_arr > t_dep:
                base_time_min = float(t_arr - t_dep)

            # Distance via Haversine
            distance_km = distance_engine.haversine((sta.lat, sta.lon), (stb.lat, stb.lon))

            if base_time_min is None:
                # Fallback: distance / default metro speed
                hours = distance_km / max(METRO_DEFAULT_SPEED_KMPH, 1e-3)
                base_time_min = hours * 60.0

            key = (stop_a, stop_b)
            prev = edges.get(key)
            if prev is None or base_time_min < prev[1]:
                edges[key] = (distance_km, base_time_min, route_id, trip_id)

    print(f"[GTFS] Built {len(edges)} directed metro edges from stop_times.")

    result: List[Tuple[str, str, float, float, Optional[str], Optional[str]]] = []
    for (sa, sb), (dist_km, base_min, route_id, trip_id) in edges.items():
        result.append((sa, sb, dist_km, base_min, route_id, trip_id))

    return result


def build_metro_edges(
    base_dir: str = ".",
) -> List[MetroEdge]:
    """
    High-level helper that returns MetroEdge objects, resolved to
    human-readable station names.
    """
    stations = build_metro_stations(base_dir=base_dir)
    edges_raw = get_adjacent_station_edges(base_dir=base_dir)

    id_to_station = stations
    metro_edges: List[MetroEdge] = []

    for stop_a, stop_b, dist_km, base_min, route_id, trip_id in edges_raw:
        if stop_a not in id_to_station or stop_b not in id_to_station:
            continue
        sa = id_to_station[stop_a]
        sb = id_to_station[stop_b]
        metro_edges.append(
            MetroEdge(
                source_name=sa.name,
                destination_name=sb.name,
                distance_km=dist_km,
                base_time_min=base_min,
                route_id=route_id,
                trip_id=trip_id,
            )
        )

    print(f"[GTFS] Resolved {len(metro_edges)} metro edges with station names.")
    return metro_edges


