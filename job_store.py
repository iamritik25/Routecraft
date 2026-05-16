"""
Async job store for long-running route calculations (202 Accepted pattern).
Clients submit a job, get a job_id, then poll GET /v1/jobs/<job_id> for results.
In-memory; swap _store dict for Redis hash in production.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class Status(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Job:
    job_id: str
    status: Status = Status.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None


class JobStore:
    """Thread-safe in-memory job store. Max 2000 entries; oldest done/failed pruned."""

    MAX_JOBS = 2000

    def __init__(self) -> None:
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self) -> str:
        job_id = str(uuid.uuid4())
        with self._lock:
            self._jobs[job_id] = Job(job_id=job_id)
            self._prune()
        return job_id

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def set_processing(self, job_id: str) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].status = Status.PROCESSING

    def set_done(self, job_id: str, result: Any) -> None:
        with self._lock:
            if job_id in self._jobs:
                j = self._jobs[job_id]
                j.status = Status.DONE
                j.result = result

    def set_failed(self, job_id: str, error: str) -> None:
        with self._lock:
            if job_id in self._jobs:
                j = self._jobs[job_id]
                j.status = Status.FAILED
                j.error = error

    def _prune(self) -> None:
        if len(self._jobs) <= self.MAX_JOBS:
            return
        terminal = [
            j for j in self._jobs.values()
            if j.status in (Status.DONE, Status.FAILED)
        ]
        for j in terminal[: len(self._jobs) - self.MAX_JOBS]:
            self._jobs.pop(j.job_id, None)


# Module-level singleton
_store = JobStore()


def get_job_store() -> JobStore:
    return _store
