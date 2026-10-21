import logging
import time

import redis

from app.core.errors import RateLimitError

logger = logging.getLogger(__name__)

WINDOW_SECONDS = 60


class RateLimiter:
    """Fixed-window counter in Redis, shared by every app instance.

    Key: rl:{scope}:{identity}:{window}, where window = current minute number.
    """

    def __init__(self, client: redis.Redis) -> None:
        self.client = client

    def hit(self, scope: str, identity: str, limit: int, now: float | None = None) -> None:
        """Count this request; raise RateLimitError if it goes over the limit."""
        now = time.time() if now is None else now
        count = self._increment(scope, identity, now)
        if count is not None and count > limit:
            raise self._error(now)

    def check(self, scope: str, identity: str, limit: int, now: float | None = None) -> None:
        """Raise RateLimitError if the limit is already reached, without counting."""
        now = time.time() if now is None else now
        try:
            raw = self.client.get(self._key(scope, identity, now))
        except redis.RedisError:
            logger.warning("Rate limiter unavailable, allowing request")  # fail open
            return
        if raw is not None and int(raw) >= limit:
            raise self._error(now)

    def record(self, scope: str, identity: str, now: float | None = None) -> None:
        """Count an attempt (e.g. a failed login) without checking the limit."""
        self._increment(scope, identity, time.time() if now is None else now)

    def _increment(self, scope: str, identity: str, now: float) -> int | None:
        key = self._key(scope, identity, now)
        try:
            count = int(self.client.incr(key))
            if count == 1:
                self.client.expire(key, WINDOW_SECONDS)
            return count
        except redis.RedisError:
            # Fail open: blocking every user because Redis is down would be worse.
            logger.warning("Rate limiter unavailable, allowing request")
            return None

    @staticmethod
    def _key(scope: str, identity: str, now: float) -> str:
        return f"rl:{scope}:{identity}:{int(now // WINDOW_SECONDS)}"

    @staticmethod
    def _error(now: float) -> RateLimitError:
        retry_after = WINDOW_SECONDS - int(now % WINDOW_SECONDS)
        return RateLimitError("Too many requests, try again later", retry_after=retry_after)
