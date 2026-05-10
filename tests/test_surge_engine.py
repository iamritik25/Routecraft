"""Tests for SurgePricingEngine."""
import pytest
from surge_engine import SurgePricingEngine


@pytest.fixture
def surge():
    return SurgePricingEngine()


class TestSurgePricingEngine:
    def test_clear_weather_off_peak_is_min(self, surge):
        s = surge.get_surge(hour=3, weather="Clear", area=None)
        assert s == pytest.approx(1.0)

    def test_evening_peak_increases_surge(self, surge):
        off_peak = surge.get_surge(hour=3, weather="Clear")
        evening = surge.get_surge(hour=18, weather="Clear")
        assert evening > off_peak

    def test_heavy_rain_increases_surge(self, surge):
        clear = surge.get_surge(hour=18, weather="Clear")
        rain = surge.get_surge(hour=18, weather="Heavy Rain")
        assert rain > clear

    def test_high_demand_area_increases_surge(self, surge):
        generic = surge.get_surge(hour=8, weather="Clear", area="Somewhere")
        koramangala = surge.get_surge(hour=8, weather="Clear", area="Koramangala")
        assert koramangala > generic

    def test_surge_never_exceeds_max(self, surge):
        s = surge.get_surge(hour=18, weather="Heavy Rain", area="MG Road")
        assert s <= surge.MAX_SURGE

    def test_surge_never_below_min(self, surge):
        s = surge.get_surge(hour=3, weather="Clear", area=None)
        assert s >= surge.MIN_SURGE

    def test_labels_are_correct(self, surge):
        assert "Normal" in surge.get_surge_label(1.0)
        assert "Moderate" in surge.get_surge_label(1.4)
        assert "High" in surge.get_surge_label(1.9)
        assert "Very High" in surge.get_surge_label(2.6)
