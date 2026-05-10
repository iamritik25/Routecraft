import heapq
from dataclasses import dataclass, field
from typing import Dict, Tuple, List, Optional, Any

from graph_builder import Edge

State = Tuple[str, str]  # (location, mode)


@dataclass
class PathResult:
    path: List[State]
    edges: List[Edge]
    total_cost: float
    total_time: float
    # ETA confidence intervals (populated by attach_confidence)
    eta_p10: Optional[float] = None
    eta_p50: Optional[float] = None
    eta_p90: Optional[float] = None
    eta_confidence: Optional[str] = None

    def attach_confidence(self) -> "PathResult":
        """Compute and attach P10/P50/P90 ETA bounds from edge multipliers."""
        try:
            from services.eta_confidence import compute_eta_bounds
            tm = [e.traffic_multiplier for e in self.edges if e.traffic_multiplier > 0]
            wm = [e.weather_multiplier for e in self.edges if e.weather_multiplier > 0]
            bounds = compute_eta_bounds(self.total_time, tm, wm)
            self.eta_p10 = bounds.p10_min
            self.eta_p50 = bounds.p50_min
            self.eta_p90 = bounds.p90_min
            self.eta_confidence = bounds.confidence
        except Exception:
            pass
        return self


class RouteEngine:
    """
    Extended Dijkstra on multi-layer graph.
    Supports cost/time/balanced optimisation and Pareto-based route variants.
    """

    def __init__(self, graph: Dict[State, List[Edge]]):
        self.graph = graph

    def _reconstruct_path(
        self,
        prev: Dict[State, Optional[Tuple[State, Edge]]],
        end_state: State,
    ) -> PathResult:
        path: List[State] = []
        edges: List[Edge] = []
        cur: Optional[State] = end_state

        while cur is not None:
            prev_entry = prev.get(cur)
            path.append(cur)
            if prev_entry is None:
                break
            prev_state, edge = prev_entry
            edges.append(edge)
            cur = prev_state

        path.reverse()
        edges.reverse()

        total_cost = sum(e.cost for e in edges)
        total_time = sum(e.time_min for e in edges)
        result = PathResult(path=path, edges=edges, total_cost=total_cost, total_time=total_time)
        result.attach_confidence()
        return result

    def dijkstra(
        self,
        source_location: str,
        target_location: str,
        optimize_for: str,
        *,
        allowed_modes: Optional[set] = None,
        cost_ref: Optional[float] = None,
        time_ref: Optional[float] = None,
    ) -> Optional[PathResult]:
        dist_cost: Dict[State, float] = {}
        dist_time: Dict[State, float] = {}
        dist_score: Dict[State, float] = {}
        prev: Dict[State, Optional[Tuple[State, Edge]]] = {}

        pq: List[Tuple[float, float, State]] = []

        for state in self.graph.keys():
            if state[0] == source_location:
                if allowed_modes is not None and state[1] not in allowed_modes:
                    continue
                dist_cost[state] = 0.0
                dist_time[state] = 0.0
                dist_score[state] = 0.0
                prev[state] = None
                heapq.heappush(pq, (0.0, 0.0, state))

        visited: Dict[State, bool] = {}

        def compute_priority(c: float, t: float) -> Tuple[float, float]:
            if optimize_for == "time":
                return t, c
            if optimize_for == "cost":
                return c, t
            cr = cost_ref if cost_ref and cost_ref > 0 else 1.0
            tr = time_ref if time_ref and time_ref > 0 else 1.0
            score = 0.5 * (c / cr) + 0.5 * (t / tr)
            return score, t

        best_end: Optional[State] = None

        while pq:
            _, _, state = heapq.heappop(pq)
            if visited.get(state):
                continue
            visited[state] = True

            if state[0] == target_location:
                best_end = state
                break

            for edge in self.graph.get(state, []):
                nxt = edge.target
                if allowed_modes is not None and nxt[1] not in allowed_modes:
                    continue
                if (allowed_modes is not None and state[0] == nxt[0]
                        and state[1] != nxt[1]
                        and (state[1] not in allowed_modes or nxt[1] not in allowed_modes)):
                    continue

                new_cost = dist_cost[state] + edge.cost
                new_time = dist_time[state] + edge.time_min
                new_prio, new_sec = compute_priority(new_cost, new_time)

                if optimize_for == "cost":
                    better = new_cost < dist_cost.get(nxt, float("inf"))
                elif optimize_for == "time":
                    better = new_time < dist_time.get(nxt, float("inf"))
                else:
                    better = new_prio < dist_score.get(nxt, float("inf"))

                if better:
                    dist_cost[nxt] = new_cost
                    dist_time[nxt] = new_time
                    dist_score[nxt] = new_prio
                    prev[nxt] = (state, edge)
                    heapq.heappush(pq, (new_prio, new_sec, nxt))

        if best_end is None:
            return None
        return self._reconstruct_path(prev, best_end)

    def compute_pareto_routes(
        self,
        source_location: str,
        target_location: str,
    ) -> Dict[str, Optional[PathResult]]:
        cheapest = self.dijkstra(source_location, target_location, optimize_for="cost")
        fastest = self.dijkstra(source_location, target_location, optimize_for="time")

        cost_ref = cheapest.total_cost if cheapest else None
        time_ref = fastest.total_time if fastest else None
        balanced = self.dijkstra(
            source_location, target_location,
            optimize_for="balanced", cost_ref=cost_ref, time_ref=time_ref,
        )

        cab_only = self.dijkstra(source_location, target_location,
                                  optimize_for="time", allowed_modes={"cab"})
        metro_only = self.dijkstra(source_location, target_location,
                                    optimize_for="time", allowed_modes={"metro"})
        metro_plus_cab = self.dijkstra(source_location, target_location,
                                        optimize_for="balanced",
                                        allowed_modes={"metro", "cab", "walk"})
        bus_only = self.dijkstra(source_location, target_location,
                                  optimize_for="time", allowed_modes={"bus"})

        return {
            "cheapest": cheapest,
            "fastest": fastest,
            "balanced": balanced,
            "cab_only": cab_only,
            "metro_only": metro_only,
            "metro_plus_cab": metro_plus_cab,
            "bus_only": bus_only,
        }
