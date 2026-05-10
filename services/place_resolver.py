from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional

from gtfs_engine import normalize_station_name


@dataclass(frozen=True)
class Place:
    name: str
    lat: float
    lon: float
    place_type: str


@dataclass(frozen=True)
class ResolvedInput:
    kind: str  # "transport" | "place"
    name: str
    lat: float | None = None
    lon: float | None = None
    place_type: str | None = None


class PlaceResolver:
    def __init__(
        self,
        *,
        locations: Iterable[dict],
        alias_map: Dict[str, str],
        places_csv_path: str = "data/places.csv",
        base_dir: str = ".",
    ) -> None:
        self._locations = list(locations)
        self._alias_map = dict(alias_map or {})
        self._places_csv_path = str(places_csv_path)
        self._base_dir = base_dir

        self._lower_name_lookup: Dict[str, str] = {
            str(loc["name"]).lower(): str(loc["name"]) for loc in self._locations
        }
        self._normalized_lookup: Dict[str, str] = {}
        for loc in self._locations:
            n = normalize_station_name(str(loc["name"]))
            self._normalized_lookup.setdefault(n, str(loc["name"]))

        self._places_by_norm: Dict[str, Place] = {}
        self._load_places()

    def _load_places(self) -> None:
        path = Path(self._base_dir) / self._places_csv_path
        if not path.exists():
            self._places_by_norm = {}
            return

        out: Dict[str, Place] = {}
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = (row.get("place_name") or "").strip()
                if not name:
                    continue
                lat = row.get("latitude")
                lon = row.get("longitude")
                try:
                    lat_f = float(lat) if lat is not None else None
                    lon_f = float(lon) if lon is not None else None
                except ValueError:
                    continue
                if lat_f is None or lon_f is None:
                    continue
                ptype = (row.get("place_type") or "").strip() or "place"
                out[normalize_station_name(name)] = Place(
                    name=name,
                    lat=lat_f,
                    lon=lon_f,
                    place_type=ptype,
                )
        self._places_by_norm = out

    def resolve(self, raw: str) -> Optional[ResolvedInput]:
        raw_s = (raw or "").strip()
        if not raw_s:
            return None

        lower = raw_s.lower()
        if lower in self._lower_name_lookup:
            return ResolvedInput(kind="transport", name=self._lower_name_lookup[lower])

        if raw_s in self._alias_map:
            alias_target = self._alias_map[raw_s]
            if alias_target and alias_target.lower() in self._lower_name_lookup:
                return ResolvedInput(kind="transport", name=self._lower_name_lookup[alias_target.lower()])

        norm = normalize_station_name(raw_s)
        if norm in self._normalized_lookup:
            return ResolvedInput(kind="transport", name=self._normalized_lookup[norm])

        place = self._places_by_norm.get(norm)
        if place:
            return ResolvedInput(
                kind="place",
                name=place.name,
                lat=place.lat,
                lon=place.lon,
                place_type=place.place_type,
            )
        return None

