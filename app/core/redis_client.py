import redis

from app.core.config import settings

# Short timeouts: if Redis is slow or down we want to fall back quickly, not hang the request.
redis_client = redis.Redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_timeout=0.5,
    socket_connect_timeout=0.5,
)


def get_redis() -> redis.Redis:
    return redis_client
