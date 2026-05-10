"""Pytest configuration and shared fixtures for RouteCraft tests."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from graph_builder import Edge


@pytest.fixture
def simple_graph():
    """Minimal 3-node (A→B→C) graph with cab and walk edges."""
    modes = ["walk", "auto", "cab", "bus", "metro"]
    nodes = ["A", "B", "C"]
    graph = {(n, m): [] for n in nodes for m in modes}
    # cab: A→B (10 min, ₹50) and B→C (15 min, ₹70)
    graph[("A", "cab")].append(Edge(target=("B", "cab"), time_min=10, cost=50,
                                     description="cab A to B", mode="cab",
                                     traffic_multiplier=1.0, weather_multiplier=1.0))
    graph[("B", "cab")].append(Edge(target=("C", "cab"), time_min=15, cost=70,
                                     description="cab B to C", mode="cab",
                                     traffic_multiplier=1.2, weather_multiplier=1.0))
    # walk: A→B (30 min, ₹0) and B→C (45 min, ₹0)
    graph[("A", "walk")].append(Edge(target=("B", "walk"), time_min=30, cost=0,
                                      description="walk A to B", mode="walk",
                                      traffic_multiplier=1.0, weather_multiplier=1.0))
    graph[("B", "walk")].append(Edge(target=("C", "walk"), time_min=45, cost=0,
                                      description="walk B to C", mode="walk",
                                      traffic_multiplier=1.0, weather_multiplier=1.0))
    return graph


@pytest.fixture
def sample_locations():
    return [
        {"name": "Koramangala", "lat": 12.935, "lon": 77.624, "is_metro_station": False, "is_bus_hub": True},
        {"name": "MG Road", "lat": 12.975, "lon": 77.607, "is_metro_station": True, "is_bus_hub": True},
        {"name": "Whitefield", "lat": 12.969, "lon": 77.750, "is_metro_station": False, "is_bus_hub": False},
    ]
