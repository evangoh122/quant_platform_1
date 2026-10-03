"""limits.py — Rate limiting, concurrency, and resource caps.

Implements per-user and per-IP token-bucket/sliding-window limits.
Limit-store failure fails closed for chat/confirmation endpoints.
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RateLimitConfig:
    """Configurable rate limit parameters."""
    # Per-user limits
    user_requests_per_minute: int = 20
    user_requests_per_hour: int = 100
    user_concurrent_requests: int = 3

    # Per-IP limits
    ip_requests_per_minute: int = 60
    ip_requests_per_hour: int = 300
    ip_concurrent_requests: int = 10

    # Token/cost budgets
    user_tokens_per_day: int = 500_000
    user_cost_per_day_cents: int = 500  # $5.00

    # Input caps
    max_message_chars: int = 4000
    max_history_turns: int = 20
    max_history_tokens: int = 6000
    max_retrieved_chunks: int = 10
    max_chunk_bytes: int = 50_000
    max_output_tokens: int = 4096
    max_tool_calls_per_turn: int = 10
    max_tool_result_bytes: int = 50_000
    max_request_wall_time_seconds: float = 120.0


@dataclass
class LimitVerdict:
    """Result of a limit check."""
    allowed: bool
    reason: str = ""
    retry_after_seconds: float = 0.0
    limit_type: str = ""


class TokenBucket:
    """Simple token bucket for rate limiting."""

    def __init__(self, rate: float, capacity: float) -> None:
        self.rate = rate  # tokens per second
        self.capacity = capacity
        self.tokens = capacity
        self.last_time = time.monotonic()

    def consume(self, tokens: float = 1.0) -> bool:
        """Try to consume tokens. Returns True if allowed."""
        now = time.monotonic()
        elapsed = now - self.last_time
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_time = now

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def wait_time(self, tokens: float = 1.0) -> float:
        """How long to wait until tokens are available."""
        if self.tokens >= tokens:
            return 0.0
        return (tokens - self.tokens) / self.rate


class SlidingWindowCounter:
    """Sliding window counter for rate limiting."""

    def __init__(self, window_seconds: float, max_count: int) -> None:
        self.window_seconds = window_seconds
        self.max_count = max_count
        self.timestamps: list[float] = []

    def check_and_increment(self) -> tuple[bool, float]:
        """Check if the request is allowed and increment counter.

        Returns (allowed, retry_after_seconds).
        """
        now = time.monotonic()
        cutoff = now - self.window_seconds

        # Remove expired entries
        self.timestamps = [t for t in self.timestamps if t > cutoff]

        if len(self.timestamps) >= self.max_count:
            # Calculate retry-after
            oldest = self.timestamps[0]
            retry_after = oldest + self.window_seconds - now
            return False, max(0.0, retry_after)

        self.timestamps.append(now)
        return True, 0.0


class RateLimiter:
    """Per-user and per-IP rate limiter.

    Uses sliding window counters for request rates and token buckets
    for concurrent request limiting. Fails closed on store errors.
    """

    def __init__(self, config: RateLimitConfig | None = None) -> None:
        self.config = config or RateLimitConfig()

        # Per-user state
        self._user_windows: dict[str, SlidingWindowCounter] = defaultdict(
            lambda: SlidingWindowCounter(60.0, self.config.user_requests_per_minute)
        )
        self._user_hourly: dict[str, SlidingWindowCounter] = defaultdict(
            lambda: SlidingWindowCounter(3600.0, self.config.user_requests_per_hour)
        )
        self._user_concurrent: dict[str, int] = defaultdict(int)
        self._user_tokens_today: dict[str, int] = defaultdict(int)
        self._user_cost_today: dict[str, int] = defaultdict(int)
        self._day_start: float = time.monotonic()

        # Per-IP state
        self._ip_windows: dict[str, SlidingWindowCounter] = defaultdict(
            lambda: SlidingWindowCounter(60.0, self.config.ip_requests_per_minute)
        )
        self._ip_hourly: dict[str, SlidingWindowCounter] = defaultdict(
            lambda: SlidingWindowCounter(3600.0, self.config.ip_requests_per_hour)
        )
        self._ip_concurrent: dict[str, int] = defaultdict(int)

    def _reset_daily_if_needed(self) -> None:
        """Reset daily counters at midnight (approximate)."""
        now = time.monotonic()
        if now - self._day_start >= 86400:
            self._user_tokens_today.clear()
            self._user_cost_today.clear()
            self._day_start = now

    def check_user(self, user_id: str) -> LimitVerdict:
        """Check per-user rate limits."""
        try:
            self._reset_daily_if_needed()

            # Concurrent requests
            if self._user_concurrent[user_id] >= self.config.user_concurrent_requests:
                return LimitVerdict(
                    allowed=False,
                    reason="Too many concurrent requests",
                    limit_type="user_concurrent",
                )

            # Per-minute rate
            window = self._user_windows[user_id]
            allowed, retry = window.check_and_increment()
            if not allowed:
                return LimitVerdict(
                    allowed=False,
                    reason="Rate limit exceeded (per-minute)",
                    retry_after_seconds=retry,
                    limit_type="user_per_minute",
                )

            # Per-hour rate
            hourly = self._user_hourly[user_id]
            allowed, retry = hourly.check_and_increment()
            if not allowed:
                return LimitVerdict(
                    allowed=False,
                    reason="Rate limit exceeded (per-hour)",
                    retry_after_seconds=retry,
                    limit_type="user_per_hour",
                )

            return LimitVerdict(allowed=True)
        except Exception as e:
            # Fail closed
            return LimitVerdict(
                allowed=False,
                reason=f"Rate limit check failed: {type(e).__name__}",
                limit_type="error",
            )

    def check_ip(self, ip_address: str) -> LimitVerdict:
        """Check per-IP rate limits."""
        try:
            # Concurrent requests
            if self._ip_concurrent[ip_address] >= self.config.ip_concurrent_requests:
                return LimitVerdict(
                    allowed=False,
                    reason="Too many concurrent requests from this IP",
                    limit_type="ip_concurrent",
                )

            # Per-minute rate
            window = self._ip_windows[ip_address]
            allowed, retry = window.check_and_increment()
            if not allowed:
                return LimitVerdict(
                    allowed=False,
                    reason="IP rate limit exceeded (per-minute)",
                    retry_after_seconds=retry,
                    limit_type="ip_per_minute",
                )

            # Per-hour rate
            hourly = self._ip_hourly[ip_address]
            allowed, retry = hourly.check_and_increment()
            if not allowed:
                return LimitVerdict(
                    allowed=False,
                    reason="IP rate limit exceeded (per-hour)",
                    retry_after_seconds=retry,
                    limit_type="ip_per_hour",
                )

            return LimitVerdict(allowed=True)
        except Exception as e:
            # Fail closed
            return LimitVerdict(
                allowed=False,
                reason=f"IP rate limit check failed: {type(e).__name__}",
                limit_type="error",
            )

    def check_all(
        self,
        user_id: str,
        ip_address: str,
    ) -> LimitVerdict:
        """Check both user and IP limits. Both must pass."""
        user_result = self.check_user(user_id)
        if not user_result.allowed:
            return user_result

        ip_result = self.check_ip(ip_address)
        if not ip_result.allowed:
            return ip_result

        return LimitVerdict(allowed=True)

    def acquire_user(self, user_id: str) -> None:
        """Acquire a concurrent request slot for a user."""
        self._user_concurrent[user_id] += 1

    def release_user(self, user_id: str) -> None:
        """Release a concurrent request slot for a user."""
        self._user_concurrent[user_id] = max(0, self._user_concurrent[user_id] - 1)

    def acquire_ip(self, ip_address: str) -> None:
        """Acquire a concurrent request slot for an IP."""
        self._ip_concurrent[ip_address] += 1

    def release_ip(self, ip_address: str) -> None:
        """Release a concurrent request slot for an IP."""
        self._ip_concurrent[ip_address] = max(0, self._ip_concurrent[ip_address] - 1)

    def record_tokens(self, user_id: str, tokens: int) -> None:
        """Record token usage for a user."""
        self._reset_daily_if_needed()
        self._user_tokens_today[user_id] += tokens

    def check_token_budget(self, user_id: str) -> LimitVerdict:
        """Check if user has exceeded daily token budget."""
        self._reset_daily_if_needed()
        if self._user_tokens_today[user_id] >= self.config.user_tokens_per_day:
            return LimitVerdict(
                allowed=False,
                reason="Daily token budget exceeded",
                limit_type="user_token_budget",
            )
        return LimitVerdict(allowed=True)


# Global singleton
_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter singleton."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter