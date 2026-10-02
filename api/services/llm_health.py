"""
llm_health.py — Tracks LLM call health (success/failure/error counts + last errors).
Used by the /api/health/full endpoint to monitor LLM reliability.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LLMHealthTracker:
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    last_error: Optional[str] = None
    last_error_time: Optional[float] = None
    last_success_time: Optional[float] = None
    errors: list[dict] = field(default_factory=list)

    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record_success(self) -> None:
        with self._lock:
            self.total_calls += 1
            self.successful_calls += 1
            self.last_success_time = time.time()

    def record_failure(self, error: str, context: str = "") -> None:
        with self._lock:
            self.total_calls += 1
            self.failed_calls += 1
            self.last_error = error
            self.last_error_time = time.time()
            self.errors.append({
                "error": error,
                "context": context,
                "time": time.time(),
            })
            if len(self.errors) > 50:
                self.errors = self.errors[-50:]

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "total_calls": self.total_calls,
                "successful_calls": self.successful_calls,
                "failed_calls": self.failed_calls,
                "success_rate": self._rate(),
                "last_error": self.last_error,
                "last_error_time": self.last_error_time,
                "last_success_time": self.last_success_time,
                "recent_errors": self.errors[-10:],
            }

    def reset(self) -> None:
        with self._lock:
            self.total_calls = 0
            self.successful_calls = 0
            self.failed_calls = 0
            self.last_error = None
            self.last_error_time = None
            self.last_success_time = None
            self.errors = []

    def _rate(self) -> float:
        if self.total_calls == 0:
            return 1.0
        return self.successful_calls / self.total_calls


_llm_tracker = LLMHealthTracker()


def get_llm_tracker() -> LLMHealthTracker:
    return _llm_tracker
