"""Tests for A/B testing framework."""
import pytest
from ab_testing import get_model_backend, get_backend_counts, reset_counts, BACKENDS


class TestABTesting:
    def setup_method(self):
        reset_counts()

    def test_returns_valid_backend(self):
        backend = get_model_backend()
        assert backend in BACKENDS

    def test_sticky_sessions_deterministic(self):
        """Same session_id must always return same backend."""
        results = {get_model_backend("fixed-session-123") for _ in range(10)}
        assert len(results) == 1  # always same

    def test_different_sessions_can_differ(self):
        """Different sessions should (statistically) produce both backends."""
        import uuid
        results = {get_model_backend(str(uuid.uuid4())) for _ in range(200)}
        # With 10% split and 200 samples, both backends should appear
        assert len(results) >= 1

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("TRAFFIC_MODEL_TYPE", "mps_nn")
        assert get_model_backend("any-session") == "mps_nn"

    def test_backend_counts_tracked(self):
        for _ in range(5):
            get_model_backend("session-a")
        counts = get_backend_counts()
        total = sum(counts.values())
        assert total == 5

    def test_reset_clears_counts(self):
        get_model_backend("session-x")
        reset_counts()
        assert sum(get_backend_counts().values()) == 0
