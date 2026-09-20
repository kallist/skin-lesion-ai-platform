"""Auth flow tests: register, duplicate, login, wrong password, logout, me."""

from __future__ import annotations

API = "/api/v1"


def test_register_creates_user_and_session(app_client, user_credentials):
    response = app_client.post(f"{API}/auth/register", json=user_credentials)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["user"]["email"] == user_credentials["email"]
    assert body["user"]["username"] == user_credentials["username"]
    assert body["csrf_token"]
    # session cookie is HttpOnly
    set_cookie = response.headers.get("set-cookie", "")
    assert "skin_session=" in set_cookie
    assert "HttpOnly" in set_cookie


def test_register_rejects_duplicate_email(app_client, user_credentials):
    assert app_client.post(f"{API}/auth/register", json=user_credentials).status_code == 201
    duplicate = dict(user_credentials, username="alice2")
    response = app_client.post(f"{API}/auth/register", json=duplicate)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"


def test_register_rejects_duplicate_username(app_client, user_credentials):
    assert app_client.post(f"{API}/auth/register", json=user_credentials).status_code == 201
    duplicate = dict(user_credentials, email="other@example.com")
    response = app_client.post(f"{API}/auth/register", json=duplicate)
    assert response.status_code == 409


def test_register_rejects_weak_password(app_client, user_credentials):
    weak = dict(user_credentials, password="12345678")
    response = app_client.post(f"{API}/auth/register", json=weak)
    assert response.status_code == 409
    assert "密码" in response.json()["error"]["message"]


def test_register_validation_error_contract(app_client):
    response = app_client.post(f"{API}/auth/register", json={"email": "not-an-email"})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert isinstance(body["error"]["details"]["fields"], list)


def test_login_with_email_and_username(app_client, registered_user, user_credentials):
    app_client.post(f"{API}/auth/logout")
    for identifier in (user_credentials["email"], user_credentials["username"]):
        response = app_client.post(
            f"{API}/auth/login",
            json={"identifier": identifier, "password": user_credentials["password"]},
        )
        assert response.status_code == 200, response.text
        assert response.json()["user"]["username"] == user_credentials["username"]
        app_client.post(f"{API}/auth/logout")


def test_login_wrong_password(app_client, registered_user, user_credentials):
    app_client.post(f"{API}/auth/logout")
    response = app_client.post(
        f"{API}/auth/login",
        json={"identifier": user_credentials["email"], "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_login_unknown_user(app_client):
    response = app_client.post(
        f"{API}/auth/login", json={"identifier": "nobody@example.com", "password": "whatever1A"}
    )
    assert response.status_code == 401


def test_logout_revokes_session(app_client, registered_user):
    assert app_client.get(f"{API}/users/me").status_code == 200
    assert app_client.post(f"{API}/auth/logout").status_code == 200
    assert app_client.get(f"{API}/users/me").status_code == 401


def test_logout_is_idempotent(app_client):
    assert app_client.post(f"{API}/auth/logout").status_code == 200
    assert app_client.post(f"{API}/auth/logout").status_code == 200


def test_session_endpoint_requires_login(app_client):
    assert app_client.get(f"{API}/auth/session").status_code == 401


def test_session_endpoint_returns_current_user(app_client, registered_user):
    response = app_client.get(f"{API}/auth/session")
    assert response.status_code == 200
    assert response.json()["user"]["username"] == registered_user["user"]["username"]


def test_protected_route_requires_authentication(app_client):
    assert app_client.get(f"{API}/users/me").status_code == 401
    assert app_client.get(f"{API}/detections").status_code == 401


def test_profile_update_requires_csrf(app_client, registered_user):
    # TestClient keeps the cookie jar, so drop the CSRF header explicitly
    response = app_client.patch(f"{API}/users/me", json={"full_name": "New Name"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_profile_update_with_csrf(app_client, registered_user):
    csrf = registered_user["csrf_token"]
    response = app_client.patch(
        f"{API}/users/me", json={"full_name": "New Name"}, headers={"X-CSRF-Token": csrf}
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == "New Name"


def test_password_is_never_stored_in_plaintext(app_client, user_credentials):
    from sqlalchemy import select

    from app.db.base import SessionLocal
    from app.db.models import User

    app_client.post(f"{API}/auth/register", json=user_credentials)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == user_credentials["email"]))
    assert user is not None
    assert user.password_hash != user_credentials["password"]
    assert user.password_hash.startswith("$argon2")
