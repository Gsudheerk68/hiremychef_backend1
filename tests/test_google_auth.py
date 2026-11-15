import uuid

from app.core.google_auth import GoogleAuthError


def _fake_google(monkeypatch, email=None, sub=None):
    info = {"sub": sub or uuid.uuid4().hex, "email": email or f"g{uuid.uuid4().hex[:8]}@example.com", "name": "Test Person"}
    monkeypatch.setattr("app.api.auth.verify_google_credential", lambda credential: info)
    return info


CRED = "x" * 40


def test_new_google_user_is_asked_for_a_role(client, monkeypatch):
    _fake_google(monkeypatch)
    r = client.post("/api/v1/auth/google", json={"credential": CRED})
    assert r.status_code == 200 and r.json()["needs_role"] is True and r.json()["token"] is None


def test_new_google_customer_gets_a_working_token_and_can_sign_in_again(client, monkeypatch):
    info = _fake_google(monkeypatch)
    r = client.post("/api/v1/auth/google", json={"credential": CRED, "role": "customer"})
    assert r.status_code == 200 and r.json()["is_new"] is True
    token = r.json()["token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["email"] == info["email"]
    again = client.post("/api/v1/auth/google", json={"credential": CRED})
    assert again.status_code == 200 and again.json()["is_new"] is False and again.json()["token"]


def test_google_only_account_cannot_use_password_login(client, monkeypatch):
    info = _fake_google(monkeypatch)
    client.post("/api/v1/auth/google", json={"credential": CRED, "role": "customer"})
    r = client.post("/api/v1/auth/login", json={"email": info["email"], "password": "anything123"})
    assert r.status_code == 401


def test_invalid_google_credential_is_rejected(client, monkeypatch):
    def boom(credential):
        raise GoogleAuthError("Invalid Google credential")
    monkeypatch.setattr("app.api.auth.verify_google_credential", boom)
    r = client.post("/api/v1/auth/google", json={"credential": CRED})
    assert r.status_code == 401
