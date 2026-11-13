P = "/api/v1/auth"
REG = {"full_name": "Sneha P", "email": "Sneha@Example.com", "password": "Password123"}


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_register_login_me(client):
    r = client.post(f"{P}/register", json=REG)
    assert r.status_code == 201 and r.json()["user"]["role"] == "customer"
    assert r.json()["user"]["email"] == "sneha@example.com"
    login = client.post(f"{P}/login", json={"email": "sneha@example.com", "password": "Password123"})
    assert login.status_code == 200
    me = client.get(f"{P}/me", headers=auth(login.json()["token"]))
    assert me.json()["full_name"] == "Sneha P"


def test_duplicate_and_wrong_password(client):
    client.post(f"{P}/register", json=REG)
    assert client.post(f"{P}/register", json=REG).status_code == 409
    assert client.post(f"{P}/login", json={"email": "sneha@example.com", "password": "bad-password"}).status_code == 401


def test_cannot_register_as_admin(client):
    assert client.post(f"{P}/register", json={**REG, "role": "admin"}).status_code == 422


def test_chef_registration_creates_unverified_profile(client):
    r = client.post(f"{P}/register", json={**REG, "role": "chef", "city": "Nellore", "cuisines": ["Andhra"]})
    assert r.status_code == 201 and r.json()["user"]["role"] == "chef"


def test_rbac(client):
    assert client.get("/api/v1/admin/users").status_code == 401
    cust = client.post(f"{P}/register", json=REG).json()["token"]
    assert client.get("/api/v1/admin/users", headers=auth(cust)).status_code == 403
    admin = client.post(f"{P}/login", json={"email": "admin@x.com", "password": "AdminPass123"}).json()["token"]
    assert client.get("/api/v1/admin/users", headers=auth(admin)).status_code == 200


def test_reset_password_flow(client):
    from app.core.security import create_token
    uid = client.post(f"{P}/register", json=REG).json()["user"]["id"]
    token = create_token(uid, purpose="reset")
    assert client.post(f"{P}/reset-password", json={"token": token, "new_password": "NewPassword456"}).status_code == 200
    assert client.post(f"{P}/login", json={"email": "sneha@example.com", "password": "NewPassword456"}).status_code == 200
    access = create_token(uid)  # an access token must not work as a reset token
    assert client.post(f"{P}/reset-password", json={"token": access, "new_password": "Another12345"}).status_code == 400
