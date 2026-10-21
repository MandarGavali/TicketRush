"""Dependency injection: FastAPI builds Session -> Repository -> Service for every request."""

from typing import Annotated

import jwt
import redis
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_session
from app.core.errors import AuthenticationError, PermissionDeniedError
from app.core.redis_client import get_redis
from app.core.security import decode_access_token
from app.domain.booking_rules import Role
from app.models import User
from app.payments.gateway import FakePaymentGateway, PaymentGateway
from app.repositories.booking_repo import BookingRepository
from app.repositories.event_repo import EventRepository
from app.repositories.seat_repo import SeatRepository
from app.repositories.user_repo import UserRepository
from app.services.auth_service import AuthService
from app.services.booking_service import BookingService
from app.services.cache_service import CacheService
from app.services.event_service import EventService
from app.services.rate_limiter import RateLimiter

SessionDep = Annotated[Session, Depends(get_session)]
RedisDep = Annotated[redis.Redis, Depends(get_redis)]

# auto_error=False: we raise our own 401 so the error body has our standard format.
bearer_scheme = HTTPBearer(auto_error=False)

_payment_gateway = FakePaymentGateway()


def get_payment_gateway() -> PaymentGateway:
    return _payment_gateway


def get_cache(client: RedisDep) -> CacheService:
    return CacheService(client, ttl_seconds=settings.event_cache_ttl_seconds)


def get_rate_limiter(client: RedisDep) -> RateLimiter:
    return RateLimiter(client)


def get_auth_service(
    session: SessionDep, limiter: Annotated[RateLimiter, Depends(get_rate_limiter)]
) -> AuthService:
    return AuthService(session, UserRepository(session), limiter)


def get_event_service(
    session: SessionDep, cache: Annotated[CacheService, Depends(get_cache)]
) -> EventService:
    return EventService(session, EventRepository(session), SeatRepository(session), cache)


def get_booking_service(
    session: SessionDep,
    cache: Annotated[CacheService, Depends(get_cache)],
    gateway: Annotated[PaymentGateway, Depends(get_payment_gateway)],
) -> BookingService:
    return BookingService(
        session,
        BookingRepository(session),
        SeatRepository(session),
        EventRepository(session),
        payment_gateway=gateway,
        cache=cache,
        hold_minutes=settings.hold_minutes,
        max_seats=settings.max_seats_per_booking,
    )


def get_current_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    if credentials is None:
        raise AuthenticationError("Missing bearer token")
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise AuthenticationError("Invalid or expired token") from None

    user = UserRepository(session).get(user_id)
    if user is None:
        raise AuthenticationError("User no longer exists")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role != Role.ADMIN:
        raise PermissionDeniedError("Admin role required")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def booking_rate_limit(
    user: CurrentUser, limiter: Annotated[RateLimiter, Depends(get_rate_limiter)]
) -> None:
    limiter.hit("booking", str(user.id), settings.booking_rate_limit_per_min)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
EventServiceDep = Annotated[EventService, Depends(get_event_service)]
BookingServiceDep = Annotated[BookingService, Depends(get_booking_service)]
