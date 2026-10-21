from collections.abc import Callable, Iterator
from typing import Any

import pytest
import redis
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.database import Base, get_session
from app.core.redis_client import get_redis
from app.core.security import hash_password
from app.domain.booking_rules import Role
from app.main import create_app
from app.models import User
from tests.integration.helpers import PASSWORD, Headers, event_payload, login, register

TABLES = "booking_seats, bookings, seats, events, users"


@pytest.fixture(scope="session")
def engine():
    # pool_size 25: the concurrency test opens 20 connections at the same time.
    engine = create_engine(settings.database_url, pool_size=25, max_overflow=5)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="session")
def session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture(scope="session")
def redis_client() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


@pytest.fixture(autouse=True)
def clean_state(engine, redis_client) -> None:
    """Every test starts with empty tables and an empty Redis."""
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    redis_client.flushdb()


@pytest.fixture
def db(session_factory) -> Iterator[Session]:
    with session_factory() as session:
        yield session


@pytest.fixture
def app(session_factory, redis_client):
    app = create_app()

    def override_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_redis] = lambda: redis_client
    return app


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client


# ---------- user and event fixtures ----------


@pytest.fixture
def make_user(client) -> Callable[[str], Headers]:
    def _make(email: str) -> Headers:
        register(client, email)
        return login(client, email)

    return _make


@pytest.fixture
def user_headers(make_user) -> Headers:
    return make_user("user@test.com")


@pytest.fixture
def admin_headers(client, db) -> Headers:
    # Admins cannot sign up through the API, so create one directly in the database.
    db.add(
        User(
            email="admin@test.com",
            password_hash=hash_password(PASSWORD),
            full_name="Admin",
            role=Role.ADMIN,
        )
    )
    db.commit()
    return login(client, "admin@test.com")


@pytest.fixture
def create_event(client, admin_headers) -> Callable[..., dict[str, Any]]:
    def _create(**overrides: Any) -> dict[str, Any]:
        response = client.post(
            "/api/v1/events", json=event_payload(**overrides), headers=admin_headers
        )
        assert response.status_code == 201, response.text
        return response.json()

    return _create
