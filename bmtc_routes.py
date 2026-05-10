import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class BmtcRoute:
    route_no: str
    url: str
    stops: List[str]


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def load_bmtc_routes(path: str | Path) -> List[BmtcRoute]:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    routes: Dict[str, Dict[str, object]] = data.get("routes", {})  # type: ignore[assignment]
    out: List[BmtcRoute] = []
    for route_no, info in routes.items():
        if not isinstance(info, dict):
            continue
        url = str(info.get("url", ""))
        stops = info.get("stops", [])
        if not isinstance(stops, list):
            continue
        stops_s = [str(x) for x in stops if str(x).strip()]
        if not stops_s:
            continue
        out.append(BmtcRoute(route_no=str(route_no), url=url, stops=stops_s))
    return out


def hub_sequence_for_route(
    route: BmtcRoute,
    *,
    hub_names: Iterable[str],
    preferred_hub_for_token: Dict[str, str] | None = None,
) -> List[str]:
    """
    Converts a list of BMTC stop names into an ordered list of known hub location names
    in your project.

    - preferred_hub_for_token maps normalized stop tokens -> canonical hub name.
    """
    hubs = list(hub_names)
    hub_norm_to_name = {_norm(h): h for h in hubs}
    preferred = preferred_hub_for_token or {}

    found: List[str] = []
    seen: set[str] = set()

    for stop in route.stops:
        stop_n = _norm(stop)
        # explicit aliases first
        if stop_n in preferred:
            hub = preferred[stop_n]
            if hub not in seen:
                found.append(hub)
                seen.add(hub)
            continue

        # substring match against hub tokens (keeps order)
        for hub_n, hub in hub_norm_to_name.items():
            if hub in seen:
                continue
            if hub_n and hub_n in stop_n:
                found.append(hub)
                seen.add(hub)
                break

    return found


def consecutive_pairs(seq: Sequence[str]) -> List[Tuple[str, str]]:
    return [(seq[i], seq[i + 1]) for i in range(len(seq) - 1)]

