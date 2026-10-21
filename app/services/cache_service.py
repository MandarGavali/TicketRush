import json
import logging
from typing import Any

import redis

logger = logging.getLogger(__name__)


def event_cache_key(event_id: int) -> str:
    return f"event:{event_id}"


class CacheService:
    """Small JSON cache on Redis. Every method fails open: Redis down means slower, never broken."""

    def __init__(self, client: redis.Redis, ttl_seconds: int = 60) -> None:
        self.client = client
        self.ttl_seconds = ttl_seconds

    def get_json(self, key: str) -> Any | None:
        try:
            raw = self.client.get(key)
        except redis.RedisError:
            logger.warning("Cache read failed for %s, falling back to the database", key)
            return None
        return json.loads(raw) if raw else None

    def set_json(self, key: str, value: Any) -> None:
        try:
            # TTL is the safety net: even if an invalidation is missed, stale data dies in 60 s.
            self.client.set(key, json.dumps(value), ex=self.ttl_seconds)
        except redis.RedisError:
            logger.warning("Cache write failed for %s", key)

    def delete(self, key: str) -> None:
        try:
            self.client.delete(key)
        except redis.RedisError:
            logger.warning("Cache delete failed for %s", key)
