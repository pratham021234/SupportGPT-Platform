"""Enterprise sliding-window rate limiter for sensitive endpoints.

Provides brute-force mitigation for authentication, credential checks,
and resource-intensive operations with configurable thresholds.
"""

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field

from app.core.errors import RateLimitExceededException
from app.core.logging import get_logger

logger = get_logger("supportgpt.rate_limiter")


@dataclass
class RateLimitBucket:
    """Tracks timestamps of attempts within a sliding time window."""

    timestamps: list[float] = field(default_factory=list)


class InMemoryRateLimiter:
    """Thread-safe, sliding-window in-memory rate limiter."""

    def __init__(self) -> None:
        self._buckets: dict[str, RateLimitBucket] = defaultdict(RateLimitBucket)
        self._lock = asyncio.Lock()

    async def check(self, key: str, max_attempts: int, window_seconds: int) -> None:
        """Check if the given key has exceeded the maximum attempts.

        Raises:
            RateLimitExceededException: If the rate limit has been exceeded.
        """
        async with self._lock:
            now = time.time()
            bucket = self._buckets[key]
            # Prune timestamps older than window
            cutoff = now - window_seconds
            bucket.timestamps = [ts for ts in bucket.timestamps if ts > cutoff]

            if len(bucket.timestamps) >= max_attempts:
                oldest_in_window = bucket.timestamps[0]
                retry_after_seconds = int(max(1, (oldest_in_window + window_seconds) - now))
                logger.warning(
                    "Rate limit exceeded for key '%s': %d attempts in %ds window (retry in %ds)",
                    key,
                    len(bucket.timestamps),
                    window_seconds,
                    retry_after_seconds,
                )
                raise RateLimitExceededException(
                    f"Too many failed attempts. Please wait {retry_after_seconds} seconds before retrying."
                )

    async def record_failure(self, key: str, window_seconds: int) -> int:
        """Record a failed attempt for the given key and return the new attempt count."""
        async with self._lock:
            now = time.time()
            bucket = self._buckets[key]
            cutoff = now - window_seconds
            bucket.timestamps = [ts for ts in bucket.timestamps if ts > cutoff]
            bucket.timestamps.append(now)
            return len(bucket.timestamps)

    async def reset(self, key: str) -> None:
        """Reset failed attempt counters for a key upon successful action."""
        async with self._lock:
            if key in self._buckets:
                del self._buckets[key]

    async def clear_all(self) -> None:
        """Clear all rate limit state (primarily for test isolation)."""
        async with self._lock:
            self._buckets.clear()


# Global singleton instance
rate_limiter = InMemoryRateLimiter()
