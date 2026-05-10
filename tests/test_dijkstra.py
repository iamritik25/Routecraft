"""Tests for the Dijkstra routing engine."""
import pytest
from route_engine import RouteEngine


class TestDijkstra:
    def test_fastest_route_found(self, simple_graph):
        engine = RouteEngine(simple_graph)
        result = engine.dijkstra("A", "C", optimize_for="time")
        assert result is not None
        assert result.path[-1][0] == "C"

    def test_fastest_uses_cab(self, simple_graph):
        engine = RouteEngine(simple_graph)
        result = engine.dijkstra("A", "C", optimize_for="time")
        assert result.total_time == pytest.approx(25.0)  # cab: 10+15

    def test_cheapest_uses_walk(self, simple_graph):
        engine = RouteEngine(simple_graph)
        result = engine.dijkstra("A", "C", optimize_for="cost")
        assert result is not None
        assert result.total_cost == pytest.approx(0.0)

    def test_no_route_returns_none(self, simple_graph):
        # Remove all edges from A
        for mode in ["walk", "auto", "cab", "bus", "metro"]:
            simple_graph[("A", mode)] = []
        engine = RouteEngine(simple_graph)
        result = engine.dijkstra("A", "C", optimize_for="time")
        assert result is None

    def test_allowed_modes_filters(self, simple_graph):
        engine = RouteEngine(simple_graph)
        # Only walk allowed — walk A→B→C = 75 min, not cab 25 min
        result = engine.dijkstra("A", "C", optimize_for="time", allowed_modes={"walk"})
        assert result is not None
        assert result.total_time == pytest.approx(75.0)

    def test_pareto_returns_seven_keys(self, simple_graph):
        engine = RouteEngine(simple_graph)
        routes = engine.compute_pareto_routes("A", "C")
        for key in ("cheapest", "fastest", "balanced", "cab_only",
                    "metro_only", "metro_plus_cab", "bus_only"):
            assert key in routes

    def test_eta_confidence_attached(self, simple_graph):
        engine = RouteEngine(simple_graph)
        result = engine.dijkstra("A", "C", optimize_for="time")
        assert result is not None
        assert result.eta_p10 is not None
        assert result.eta_p50 is not None
        assert result.eta_p90 is not None
        assert result.eta_p10 <= result.eta_p50 <= result.eta_p90

    def test_balanced_between_cheapest_and_fastest(self, simple_graph):
        engine = RouteEngine(simple_graph)
        cheapest = engine.dijkstra("A", "C", optimize_for="cost")
        fastest = engine.dijkstra("A", "C", optimize_for="time")
        balanced = engine.dijkstra("A", "C", optimize_for="balanced",
                                    cost_ref=cheapest.total_cost,
                                    time_ref=fastest.total_time)
        assert balanced is not None
        # Balanced cost should be >= cheapest cost (cheapest is optimal on cost)
        assert balanced.total_cost >= cheapest.total_cost - 0.01
