"""Tests for async JobStore."""
import pytest
import time
import threading
from job_store import JobStore, Status


@pytest.fixture
def store():
    return JobStore()


class TestJobStore:
    def test_create_returns_id(self, store):
        job_id = store.create()
        assert isinstance(job_id, str)
        assert len(job_id) > 0

    def test_new_job_is_pending(self, store):
        job_id = store.create()
        job = store.get(job_id)
        assert job is not None
        assert job.status == Status.PENDING

    def test_set_processing(self, store):
        job_id = store.create()
        store.set_processing(job_id)
        assert store.get(job_id).status == Status.PROCESSING

    def test_set_done_with_result(self, store):
        job_id = store.create()
        store.set_done(job_id, {"answer": 42})
        job = store.get(job_id)
        assert job.status == Status.DONE
        assert job.result == {"answer": 42}

    def test_set_failed_with_error(self, store):
        job_id = store.create()
        store.set_failed(job_id, "Something broke")
        job = store.get(job_id)
        assert job.status == Status.FAILED
        assert job.error == "Something broke"

    def test_missing_job_returns_none(self, store):
        assert store.get("non-existent-id") is None

    def test_thread_safe_concurrent_creates(self, store):
        ids = []
        lock = threading.Lock()

        def create():
            job_id = store.create()
            with lock:
                ids.append(job_id)

        threads = [threading.Thread(target=create) for _ in range(50)]
        for t in threads: t.start()
        for t in threads: t.join()

        assert len(ids) == 50
        assert len(set(ids)) == 50  # all unique
