from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from gtfs_engine import normalize_station_name


@dataclass(frozen=True)
class MetroStation:
    id: str
    name: str
    lat: float
    lon: float


def _strip_ns(tag: str) -> str:
    # "{namespace}tag" -> "tag"
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def load_metro_stations_from_kml(kml_path: str) -> List[MetroStation]:
    """
    Parse a KML file and extract metro stations from Placemark name + Point coordinates.
    """
    path = Path(kml_path)
    if not path.exists():
        return []

    tree = ET.parse(path)
    root = tree.getroot()

    stations: List[MetroStation] = []
    idx = 0
    # Iterate all placemarks regardless of namespace.
    for pm in root.iter():
        if _strip_ns(pm.tag) != "Placemark":
            continue
        name_el = None
        coords_el = None
        for child in pm.iter():
            t = _strip_ns(child.tag)
            if t == "name" and child.text:
                name_el = child
            if t == "coordinates" and child.text:
                coords_el = child
        if name_el is None or coords_el is None:
            continue

        name = (name_el.text or "").strip()
        coords_txt = (coords_el.text or "").strip()
        if not name or not coords_txt:
            continue
        # Format: "lon,lat,alt"
        parts = coords_txt.split(",")
        if len(parts) < 2:
            continue
        try:
            lon = float(parts[0])
            lat = float(parts[1])
        except ValueError:
            continue

        idx += 1
        stations.append(MetroStation(id=f"metro_{idx}", name=name, lat=lat, lon=lon))

    return stations


def load_metro_stations_from_csv(csv_path: str) -> List[MetroStation]:
    """
    Load metro stations from a CSV file.
    Expected columns (any of these):
      - station_name or name
      - latitude or lat
      - longitude or lon
      - id (optional)
    """
    path = Path(csv_path)
    if not path.exists():
        return []

    stations: List[MetroStation] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        idx = 0
        for row in reader:
            name = (row.get("station_name") or row.get("name") or "").strip()
            if not name:
                continue
            lat_raw = row.get("latitude") or row.get("lat")
            lon_raw = row.get("longitude") or row.get("lon")
            if lat_raw is None or lon_raw is None:
                continue
            try:
                lat = float(lat_raw)
                lon = float(lon_raw)
            except ValueError:
                continue
            idx += 1
            sid = (row.get("id") or "").strip() or f"metro_{idx}"
            stations.append(MetroStation(id=sid, name=name, lat=lat, lon=lon))
    return stations


def load_metro_stations(metro_dir: str = "data/metro") -> List[MetroStation]:
    """
    Prefer CSV if present, otherwise fall back to the first KML file.
    """
    d = Path(metro_dir)
    if not d.exists():
        return []

    csv_files = sorted(d.glob("*.csv"))
    if csv_files:
        return load_metro_stations_from_csv(str(csv_files[0]))

    kml_files = sorted(d.glob("*.kml"))
    if kml_files:
        return load_metro_stations_from_kml(str(kml_files[0]))

    return []


def build_station_lookup(stations: List[MetroStation]) -> Dict[str, MetroStation]:
    """
    Map normalized station name -> station object.
    """
    out: Dict[str, MetroStation] = {}
    for s in stations:
        out[normalize_station_name(s.name)] = s
    return out

