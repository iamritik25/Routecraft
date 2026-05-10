"""Tests for ETA confidence interval computation."""
import pytest
from services.eta_confidence import compute_eta_bounds


class TestETAConfidence:
    def test_p10_le_p50_le_p90(self):
        bounds = compute_eta_bounds(60.0, [1.0, 1.2, 1.5], [1.0, 1.0, 1.1])
        assert bounds.p10_min <= bounds.p50_min <= bounds.p90_min

    def test_p50_equals_total_time(self):
        bounds = compute_eta_bounds(45.0, [1.0, 1.2], [1.0, 1.0])
        assert bounds.p50_min == pytest.approx(45.0)

    def test_empty_multipliers_gives_low_confidence(self):
        bounds = compute_eta_bounds(30.0, [], [])
        assert bounds.confidence == "low"

    def test_uniform_multipliers_gives_high_confidence(self):
        # All multipliers identical → zero variance → high confidence
        bounds = compute_eta_bounds(30.0, [1.2] * 20, [1.0] * 20)
        assert bounds.confidence == "high"

    def test_highly_variable_gives_low_confidence(self):
        # Wide spread of multipliers → low confidence, wide interval
        bounds = compute_eta_bounds(30.0, [1.0, 1.8, 1.0, 2.0, 1.0], [1.0] * 5)
        assert bounds.confidence == "low"
        assert bounds.spread_min > 5.0

    def test_zero_total_time_safe(self):
        bounds = compute_eta_bounds(0.0, [], [])
        assert bounds.p50_min == 0.0
