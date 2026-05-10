import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


class DataLoader:
    """Utility class to load JSON datasets and GTFS feeds."""

    def __init__(self, base_dir: str = ".") -> None:
        self.base_path = Path(base_dir)

    def load_locations(self, filename: str = "locations.json") -> List[Dict[str, Any]]:
        """Load the Bangalore locations dataset."""
        path = self.base_path / filename
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    # ---- GTFS helpers -------------------------------------------------

    def _gtfs_path(self, gtfs_folder: str, filename: str) -> Path:
        return self.base_path / gtfs_folder / filename

    def parse_stops(self, gtfs_folder: str) -> List[Dict[str, Any]]:
        path = self._gtfs_path(gtfs_folder, "stops.txt")
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            return [row for row in reader]

    def parse_routes(self, gtfs_folder: str) -> List[Dict[str, Any]]:
        path = self._gtfs_path(gtfs_folder, "routes.txt")
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            return [row for row in reader]

    def parse_trips(self, gtfs_folder: str) -> List[Dict[str, Any]]:
        path = self._gtfs_path(gtfs_folder, "trips.txt")
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            return [row for row in reader]

    def parse_stop_times(self, gtfs_folder: str) -> List[Dict[str, Any]]:
        path = self._gtfs_path(gtfs_folder, "stop_times.txt")
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            return [row for row in reader]

    def load_gtfs_data(self, gtfs_folder: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        Convenience loader for a GTFS folder. Missing files simply
        result in empty lists so callers can fail gracefully.
        """
        return {
            "stops": self.parse_stops(gtfs_folder),
            "routes": self.parse_routes(gtfs_folder),
            "trips": self.parse_trips(gtfs_folder),
            "stop_times": self.parse_stop_times(gtfs_folder),
        }

    # ---- Curated fallback datasets ------------------------------------

    def _data_path(self, filename: str) -> Path:
        return self.base_path / "data" / filename

    def load_bmtc_airport_routes(self, filename: str = "bmtc_airport_routes.json") -> List[Dict[str, Any]]:
        """
        Load curated BMTC airport routes dataset, if present.
        """
        path = self._data_path(filename)
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("routes", []) if isinstance(data, dict) else []

    def load_aliases(self, filename: str = "location_aliases.json") -> Dict[str, str]:
        """
        Load location alias mapping (alias -> canonical name).
        """
        path = self._data_path(filename)
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
        return {}

    def load_landmark_connectors(self, filename: str = "landmark_connectors.json") -> List[Dict[str, Any]]:
        """
        Optional curated connectors between landmarks and hubs.
        """
        path = self._data_path(filename)
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        return data.get("connectors", []) if isinstance(data, dict) else []

