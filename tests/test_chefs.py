from datetime import date, datetime, timedelta, timezone
from app.models import Booking, BookingStatus, ChefProfile, User

REG = "/api/v1/auth/register"
H = lambda t: {"Authorization": f"Bearer {t}"}


def make_chef(client, name, city, cuisines, price=2000, years=5, verify=True):
    r = client.post(REG, json={"full_name": name, "email": f"{name.split()[0].lower()}@x.com", "password": "Password123",
                               "role": "chef", "city": city, "cuisines": cuisines, "years_experience": years}).json()
    with client.Session() as db:
        p = db.query(ChefProfile).filter_by(user_id=r["user"]["id"]).one()
        p.price_per_session = price
        p.is_verified = verify
        db.commit()
        pid = p.id
    return pid, r["token"]


def admin_token(client):
    return client.post("/api/v1/auth/login", json={"email": "admin@x.com", "password": "AdminPass123"}).json()["token"]


def test_only_verified_listed_and_admin_can_verify(client):
    pid, _ = make_chef(client, "Ravi Kumar", "Nellore", ["Andhra"], verify=False)
    assert client.get("/api/v1/chefs").json()["total"] == 0
    assert client.get(f"/api/v1/chefs/{pid}").status_code == 404
    admin = admin_token(client)
    assert client.post(f"/api/v1/admin/chefs/{pid}/verify", headers=H(admin)).json()["verified"] is True
    assert client.get("/api/v1/chefs").json()["total"] == 1
    assert client.get(f"/api/v1/chefs/{pid}").json()["name"] == "Ravi Kumar"


def test_verify_requires_admin(client):
    pid, token = make_chef(client, "Ravi Kumar", "Nellore", ["Andhra"], verify=False)
    assert client.post(f"/api/v1/admin/chefs/{pid}/verify", headers=H(token)).status_code == 403


def test_filters_sort_pagination(client):
    make_chef(client, "Ravi Kumar", "Nellore", ["South Indian", "Andhra"], price=2500, years=12)
    make_chef(client, "Ayesha Khan", "Hyderabad", ["Mughlai", "Biryani"], price=3500, years=9)
    make_chef(client, "Lakshmi Devi", "Nellore", ["Vegetarian"], price=1800, years=20)
    g = lambda **p: client.get("/api/v1/chefs", params=p).json()
    assert g()["total"] == 3
    assert {c["name"] for c in g(city="nellore")["items"]} == {"Ravi Kumar", "Lakshmi Devi"}
    assert [c["name"] for c in g(cuisine="biryani")["items"]] == ["Ayesha Khan"]
    assert [c["name"] for c in g(q="lakshmi")["items"]] == ["Lakshmi Devi"]
    assert [c["price"] for c in g(sort="price_asc")["items"]] == [1800, 2500, 3500]
    assert g(max_price=2500)["total"] == 2 and g(min_experience=10)["total"] == 2
    p = g(sort="price_asc", page=2, page_size=2)
    assert p["pages"] == 2 and [c["price"] for c in p["items"]] == [3500]
    assert client.get("/api/v1/chefs", params={"sort": "bogus"}).status_code == 422


def test_chef_updates_own_profile_only(client):
    pid, token = make_chef(client, "Ravi Kumar", "Nellore", ["Andhra"])
    r = client.put("/api/v1/chefs/me", headers=H(token), json={"bio": "Hello", "price_per_session": 3000, "cuisines": [" Andhra ", "Biryani"], "is_verified": True})
    assert r.status_code == 200 and r.json()["price"] == 3000 and r.json()["cuisines"] == ["Andhra", "Biryani"]
    assert client.put("/api/v1/chefs/me", headers=H(token), json={"price_per_session": -5}).status_code == 422
    cust = client.post(REG, json={"full_name": "Sneha P", "email": "s@x.com", "password": "Password123"}).json()["token"]
    assert client.put("/api/v1/chefs/me", headers=H(cust), json={"bio": "x"}).status_code == 403
    assert client.put("/api/v1/chefs/me", json={"bio": "x"}).status_code == 401


def test_availability_block_booked_and_filter(client):
    pid, token = make_chef(client, "Ravi Kumar", "Nellore", ["Andhra"])
    d1, d2 = date.today() + timedelta(days=5), date.today() + timedelta(days=6)
    assert client.post("/api/v1/chefs/me/availability/block", headers=H(token), json={"dates": [d1.isoformat()]}).status_code == 204
    with client.Session() as db:  # an accepted booking on d2
        cid = db.query(User).filter_by(email="admin@x.com").one().id
        db.add(Booking(customer_id=cid, chef_id=pid, service_type="Dinner", event_date=datetime.combine(d2, datetime.min.time(), tzinfo=timezone.utc),
                       guests=4, location="Nellore", status=BookingStatus.accepted))
        db.commit()
    a = client.get(f"/api/v1/chefs/{pid}/availability").json()
    assert a["blocked"] == [d1.isoformat()] and a["booked"] == [d2.isoformat()]
    free = date.today() + timedelta(days=9)
    for busy in (d1, d2):
        assert client.get("/api/v1/chefs", params={"available_on": busy.isoformat()}).json()["total"] == 0
    assert client.get("/api/v1/chefs", params={"available_on": free.isoformat()}).json()["total"] == 1
    client.post("/api/v1/chefs/me/availability/unblock", headers=H(token), json={"dates": [d1.isoformat()]})
    assert client.get(f"/api/v1/chefs/{pid}/availability").json()["blocked"] == []


def test_recommended_and_route_order(client):
    make_chef(client, "Ravi Kumar", "Nellore", ["Andhra"])
    assert len(client.get("/api/v1/chefs/recommended").json()) == 1
    assert client.get("/api/v1/chefs/999").status_code == 404
