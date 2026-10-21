from tests.integration.helpers import login, register


def test_register_returns_user_without_password_hash(client):
    body = register(client, "Asha@Example.com")
    assert body["email"] == "asha@example.com"  # stored lower-case
    assert body["role"] == "USER"
    assert "password" not in body
    assert "password_hash" not in body


def test_duplicate_email_is_409(client):
    register(client, "asha@example.com")
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "ASHA@example.com", "password": "password123", "full_name": "Asha"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_TAKEN"


def test_short_password_is_422(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "a@example.com", "password": "short", "full_name": "A"},
    )
    assert response.status_code == 422


def test_login_and_me(client):
    register(client, "asha@example.com")
    headers = login(client, "asha@example.com")
    response = client.get("/api/v1/users/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["email"] == "asha@example.com"


def test_wrong_password_and_unknown_email_get_the_same_401(client):
    register(client, "asha@example.com")
    wrong_password = client.post(
        "/api/v1/auth/login", json={"email": "asha@example.com", "password": "wrong-pass"}
    )
    unknown_email = client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong-pass"}
    )
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json()["error"]["message"] == unknown_email.json()["error"]["message"]


def test_me_without_token_is_401(client):
    response = client.get("/api/v1/users/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_me_with_garbage_token_is_401(client):
    response = client.get("/api/v1/users/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401


def test_sixth_failed_login_in_a_minute_is_429(client):
    register(client, "asha@example.com")
    bad = {"email": "asha@example.com", "password": "wrong-pass"}
    for _ in range(5):
        assert client.post("/api/v1/auth/login", json=bad).status_code == 401

    # Even the correct password is refused now: the IP is locked out for this minute.
    response = client.post(
        "/api/v1/auth/login", json={"email": "asha@example.com", "password": "password123"}
    )
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"
    assert 0 < int(response.headers["Retry-After"]) <= 60


def test_successful_logins_are_not_rate_limited(client):
    register(client, "asha@example.com")
    for _ in range(8):
        login(client, "asha@example.com")
