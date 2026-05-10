from __future__ import annotations

from data_loader import DataLoader
from graph_builder import MultiLayerGraphBuilder
from route_engine import RouteEngine


def run_sample() -> None:
    dl = DataLoader(".")
    locations = dl.load_locations()
    builder = MultiLayerGraphBuilder(locations, base_dir=".")
    graph = builder.build_graph(hour=9, weather="Clear")

    engine = RouteEngine(graph)
    source = "Majestic"
    destination = "Kengeri"
    result = engine.dijkstra(source, destination, optimize_for="time")
    if result is None:
        print("No route found.")
        return

    print(f"Route {source} -> {destination}")
    print(f"Total time: {result.total_time:.1f} min")
    print(f"Total cost: {result.total_cost:.1f}")
    print("Modes used:", sorted(set(s[1] for s in result.path)))

    for i, e in enumerate(result.edges):
        a = result.path[i]
        b = result.path[i + 1]
        # Print in a wrapped-safe way (PowerShell consoles often wrap long lines
        # in confusing ways). Keep each line short.
        print(f"{i+1}. {a[0]} ({a[1]}) -> {b[0]} ({b[1]})")
        print(f"   - {e.description}")
        print(f"   - time: {e.time_min:.1f} min, cost: INR {e.cost:.1f}")


if __name__ == "__main__":
    run_sample()

