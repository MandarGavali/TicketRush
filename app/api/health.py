import logging

import redis
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import RedisDep, SessionDep

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health")
def health(session: SessionDep, client: RedisDep) -> JSONResponse:
    """Postgres is required (source of truth); Redis is optional (cache and limits fail open)."""
    try:
        session.execute(text("SELECT 1"))
        postgres = "ok"
    except SQLAlchemyError:
        logger.warning("Health check: Postgres is down")
        postgres = "down"

    try:
        client.ping()
        redis_status = "ok"
    except redis.RedisError:
        logger.warning("Health check: Redis is down")
        redis_status = "down"

    if postgres == "down":
        overall, code = "down", 503
    elif redis_status == "down":
        overall, code = "degraded", 200
    else:
        overall, code = "ok", 200
    body = {"status": overall, "postgres": postgres, "redis": redis_status}
    return JSONResponse(status_code=code, content=body)
