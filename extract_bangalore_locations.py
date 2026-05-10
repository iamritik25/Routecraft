import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _norm(s: Any) -> str:
    return str(s or "").strip()


def _lower(s: Any) -> str:
    return _norm(s).lower()


def _pick_key(row: Dict[str, Any], candidates: Iterable[str]) -> Optional[str]:
    keys_l = {k.lower(): k for k in row.keys()}
    for c in candidates:
        k = keys_l.get(c.lower())
        if k is not None:
            return k
    return None


def _to_float(v: Any) -> Optional[float]:
    s = _norm(v)
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _is_bangalore_row(row: Dict[str, Any]) -> bool:
    hay = " | ".join([_lower(v) for v in row.values()])
    # Covers common variants used in datasets.
    return any(
        token in hay
        for token in (
            "bengaluru",
            "bangalore",
            "bengaluru urban",
            "bengaluru rural",
            "bangalore urban",
            "bangalore rural",
        )
    )


def _row_to_location(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    lat_k = _pick_key(row, ("lat", "latitude", "y", "y_coord", "lat_dd"))
    lon_k = _pick_key(row, ("lon", "lng", "longitude", "x", "x_coord", "lon_dd"))
    name_k = _pick_key(row, ("name", "location", "place", "town", "village", "ward", "station"))

    if lat_k is None or lon_k is None:
        return None

    lat = _to_float(row.get(lat_k))
    lon = _to_float(row.get(lon_k))
    if lat is None or lon is None:
        return None

    name = _norm(row.get(name_k)) if name_k else ""
    if not name:
        # Try a couple more descriptive fields if name wasn't found
        alt_k = _pick_key(row, ("subdistrict", "taluk", "hobli", "district"))
        name = _norm(row.get(alt_k)) if alt_k else ""
    if not name:
        return None

    return {"name": name, "lat": lat, "lon": lon}


def load_rows(path: Path) -> List[Dict[str, Any]]:
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            # Support {"rows": [...]} / {"data": [...]} shapes
            for key in ("rows", "data", "features"):
                if key in data and isinstance(data[key], list):
                    data = data[key]
                    break
        if not isinstance(data, list):
            raise ValueError("JSON must be a list of rows (objects).")
        out: List[Dict[str, Any]] = []
        for item in data:
            if isinstance(item, dict):
                out.append(item)
        return out

    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            return [dict(r) for r in reader]

    raise ValueError("Unsupported file type. Export your dataset to .csv or .json first.")


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python extract_bangalore_locations.py <karnataka_dataset.csv|.json> [output_locations.json]")
        return 2

    inp = Path(sys.argv[1]).expanduser().resolve()
    outp = Path(sys.argv[2]).expanduser().resolve() if len(sys.argv) >= 3 else (Path.cwd() / "locations.json").resolve()

    rows = load_rows(inp)
    bangalore_rows = [r for r in rows if _is_bangalore_row(r)]

    locs: List[Dict[str, Any]] = []
    seen: set[Tuple[str, float, float]] = set()
    for r in bangalore_rows:
        loc = _row_to_location(r)
        if not loc:
            continue
        key = (_lower(loc["name"]), round(float(loc["lat"]), 6), round(float(loc["lon"]), 6))
        if key in seen:
            continue
        seen.add(key)
        locs.append(loc)

    if not locs:
        print("No Bengaluru/Bangalore rows found with (name, lat, lon).")
        print("Tip: ensure your export includes columns like name + latitude + longitude, and district/city mentions Bengaluru/Bangalore.")
        return 1

    outp.write_text(json.dumps(locs, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(locs)} Bangalore locations to: {outp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

