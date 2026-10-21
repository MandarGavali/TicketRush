from fastapi.testclient import TestClient

from app.core.redis_client import get_redis
from tests.integration.helpers import DEAD_REDIS


def test_health_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "postgres": "ok", "redis": "ok"}


def test_health_degraded_when_redis_is_down(app, client):
    app.dependency_overrides[get_redis] = lambda: DEAD_REDIS
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "degraded", "postgres": "ok", "redis": "down"}


def test_request_id_is_generated_and_echoed(client):
    assert client.get("/health").headers["X-Request-ID"]
    response = client.get("/health", headers={"X-Request-ID": "abc-123"})
    assert response.headers["X-Request-ID"] == "abc-123"


def test_unknown_route_uses_error_format(client):
    response = client.get("/nope", headers={"X-Request-ID": "rid-1"})
    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "NOT_FOUND", "message": "Not Found", "request_id": "rid-1"}
    }


def test_validation_error_uses_error_format(client):
    response = client.post("/api/v1/auth/register", json={"email": "not-an-email"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert "body.email" in error["message"]
    assert "body.password" in error["message"]


def test_unexpected_error_returns_generic_500(app):
    @app.get("/boom")
    def boom():
        raise RuntimeError("secret internal detail")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")
    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "INTERNAL_ERROR"
    assert "secret" not in error["message"]  # no internals leak to the client
