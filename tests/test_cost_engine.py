"""Tests for CostEngine fare calculations."""
import pytest
from cost_engine import CostEngine


@pytest.fixture
def engine():
    return CostEngine()


class TestCostEngine:
    def test_walk_is_always_free(self, engine):
        assert engine.cost("walk", 0.0) == 0.0
        assert engine.cost("walk", 10.0) == 0.0
        assert engine.cost("walk", 10.0, traffic_mult=2.0, weather_mult=2.0) == 0.0

    def test_cab_has_base_fare(self, engine):
        cost = engine.cost("cab", 0.0)
        assert cost == pytest.approx(CostEngine.BASE_FARE["cab"])

    def test_longer_distance_costs_more(self, engine):
        short = engine.cost("cab", 1.0)
        long = engine.cost("cab", 20.0)
        assert long > short

    def test_surge_increases_cab_cost(self, engine):
        normal = engine.cost("cab", 5.0, traffic_mult=1.0, weather_mult=1.0)
        surge = engine.cost("cab", 5.0, traffic_mult=2.0, weather_mult=1.5)
        assert surge > normal

    def test_metro_does_not_surge(self, engine):
        """Metro cost is fixed — traffic and weather don't add surge."""
        normal = engine.cost("metro", 10.0, traffic_mult=1.0, weather_mult=1.0)
        heavy = engine.cost("metro", 10.0, traffic_mult=3.0, weather_mult=2.0)
        assert normal == pytest.approx(heavy)

    def test_bus_does_not_surge(self, engine):
        normal = engine.cost("bus", 10.0, traffic_mult=1.0)
        heavy = engine.cost("bus", 10.0, traffic_mult=3.0)
        assert normal == pytest.approx(heavy)

    def test_auto_cheaper_than_cab_same_distance(self, engine):
        auto_cost = engine.cost("auto", 5.0)
        cab_cost = engine.cost("cab", 5.0)
        assert auto_cost < cab_cost

    def test_all_modes_positive(self, engine):
        for mode in ["walk", "auto", "cab", "metro", "bus"]:
            assert engine.cost(mode, 5.0) >= 0.0
