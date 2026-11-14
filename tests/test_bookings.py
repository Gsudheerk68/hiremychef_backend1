from datetime import date, timedelta
from tests.test_chefs import H, REG, admin_token, make_chef

B = "/api/v1/bookings"


def day(n):
    return date.today() + timedelta(days=n)


def customer(client, email="sneha@x.com"):
    return client.post(REG, json={"full_name": "Sneha P", "email": email, "password": "Password123"}).json()["token"]


def payload(chef_id, n=10, **kw):
    return {"chef_id": chef_id, "service_type": "Family dinner", "event_date": f"{day(n).isoformat()}T19:00:00",
            "guests": 6, "location": "Nellore, near bus stand", "cuisine": "Andhra", "estimated_price": 1, **kw}


def test_estimate_and_server_side_price(client):
    pid, _ = make_chef(client, "Ravi Kumar", "Nellore", ["Andhra"], price=2500)
    c = customer(client)
    est = client.post(f"{B}/estimate", headers=H(c), json={"chef_id": pid, "guests": 10, "service_type": "Wedding / Reception"})
    assert est.json()["estimated_price"] == 4650  # (2500 + 600) * 1.5
    r = client.post(B, headers=H(c), json=payload(pid, guests=10))
    assert r.status_code == 201
    b = r.json()
    assert b["estimated_price"] == 3100 and b["status"] == "Pending" and b["chef_name"] == "Ravi Kumar"
    assert b["customer_name"] == "Sneha P" and b["event_date"] == f"{day(10).isoformat()}T19:00:00" and b["reviewed"] is False


def test_create_validation_and_permissions(client):
    pid, chef_token = make_chef(client, "Ravi Kumar", "Nellore", ["Andhra"])
    hidden, _ = make_chef(client, "Hidden Chef", "Nellore", ["Andhra"], verify=False)
    c = customer(client)
    assert client.post(B, json=payload(pid)).status_code == 401
    assert client.post(B, headers=H(chef_token), json=payload(pid)).status_code == 403
    assert client.post(B, headers=H(c), json=payload(hidden)).status_code == 404
    assert client.post(B, headers=H(c), json=payload(pid, n=-2)).status_code == 422
    assert client.post(B, headers=H(c), json=payload(pid, service_type="Space party")).status_code == 422
    assert client.post(B, headers=H(c), json=payload(pid, guests=0)).status_code == 422


def test_blocked_date_returns_409(client):
    pid, chef_token = make_chef(client, "Ravi Kumar", "Nellore", ["Andhra"])
    client.post("/api/v1/chefs/me/availability/block", headers=H(chef_token), json={"dates": [day(10).isoformat()]})
    assert client.post(B, headers=H(customer(client)), json=payload(pid)).status_code == 409


def test_lists_are_filtered_by_token(client):
    pid, chef_token = make_chef(client, "Ravi Kumar", "Nellore", ["Andhra"])
    other_chef, other_token = make_chef(client, "Ayesha Khan", "Hyderabad", ["Mughlai"])
    a, b = customer(client, "a@x.com"), customer(client, "b@x.com")
    client.post(B, headers=H(a), json=payload(pid))
    assert len(client.get(B, headers=H(a)).json()) == 1
    assert client.get(B, headers=H(b)).json() == []
    assert len(client.get(B, headers=H(chef_token)).json()) == 1
    assert client.get(B, headers=H(other_token)).json() == []
    assert len(client.get("/api/v1/admin/bookings", headers=H(admin_token(client))).json()) == 1
    assert client.get("/api/v1/admin/bookings", headers=H(a)).status_code == 403


def test_status_flow_and_permissions(client):
    pid, chef_token = make_chef(client, "Ravi Kumar", "Nellore", ["Andhra"])
    _, other_chef = make_chef(client, "Ayesha Khan", "Hyderabad", ["Mughlai"])
    c = customer(client)
    bid = client.post(B, headers=H(c), json=payload(pid)).json()["id"]
    assert client.post(f"{B}/{bid}/accept", headers=H(c)).status_code == 403        # customer cannot accept
    assert client.post(f"{B}/{bid}/accept", headers=H(other_chef)).status_code == 404  # unrelated chef sees nothing
    assert client.post(f"{B}/{bid}/complete", headers=H(chef_token)).status_code == 409  # still Pending
    assert client.post(f"{B}/{bid}/accept", headers=H(chef_token)).json()["status"] == "Accepted"
    assert client.post(f"{B}/{bid}/reject", headers=H(chef_token)).status_code == 409
    assert client.post(f"{B}/{bid}/complete", headers=H(chef_token)).json()["status"] == "Completed"
    assert client.post(f"{B}/{bid}/cancel", headers=H(c)).status_code == 409
    assert client.post(f"{B}/{bid}/explode", headers=H(c)).status_code == 422
    r2 = client.post(B, headers=H(c), json=payload(pid, n=20)).json()["id"]
    assert client.post(f"{B}/{r2}/cancel", headers=H(c)).json()["status"] == "Cancelled"
    r3 = client.post(B, headers=H(c), json=payload(pid, n=30)).json()["id"]
    assert client.post(f"{B}/{r3}/reject", headers=H(chef_token)).json()["status"] == "Rejected"


def test_accepted_booking_blocks_the_day(client):
    pid, chef_token = make_chef(client, "Ravi Kumar", "Nellore", ["Andhra"])
    a, b = customer(client, "a@x.com"), customer(client, "b@x.com")
    first = client.post(B, headers=H(a), json=payload(pid)).json()["id"]
    second = client.post(B, headers=H(b), json=payload(pid, event_date=f"{day(10).isoformat()}T12:00:00")).json()["id"]
    assert client.post(f"{B}/{first}/accept", headers=H(chef_token)).status_code == 200
    assert client.post(f"{B}/{second}/accept", headers=H(chef_token)).status_code == 409  # same day already taken
    assert client.post(B, headers=H(b), json=payload(pid)).status_code == 409             # new requests rejected too
    avail = client.get(f"/api/v1/chefs/{pid}/availability").json()
    assert avail["booked"] == [day(10).isoformat()]
    assert client.get("/api/v1/chefs", params={"available_on": day(10).isoformat()}).json()["total"] == 0
    client.post(f"{B}/{first}/cancel", headers=H(a))  # cancelling frees the day again
    assert client.get("/api/v1/chefs", params={"available_on": day(10).isoformat()}).json()["total"] == 1


def test_reviews_flow_updates_rating(client):
    pid, chef_token = make_chef(client, "Ravi Kumar", "Nellore", ["Andhra"])
    c, stranger = customer(client), customer(client, "z@x.com")
    bid = client.post(B, headers=H(c), json=payload(pid)).json()["id"]
    review = {"booking_id": bid, "rating": 4, "comment": "Great food"}
    assert client.post("/api/v1/reviews", headers=H(c), json=review).status_code == 409   # not completed yet
    client.post(f"{B}/{bid}/accept", headers=H(chef_token)); client.post(f"{B}/{bid}/complete", headers=H(chef_token))
    assert client.post("/api/v1/reviews", headers=H(c), json={**review, "rating": 6}).status_code == 422
    assert client.post("/api/v1/reviews", headers=H(stranger), json=review).status_code == 404
    assert client.post("/api/v1/reviews", headers=H(chef_token), json=review).status_code == 403
    assert client.post("/api/v1/reviews", headers=H(c), json=review).status_code == 201
    assert client.post("/api/v1/reviews", headers=H(c), json=review).status_code == 409   # only one per booking
    chef = client.get(f"/api/v1/chefs/{pid}").json()
    assert chef["rating"] == 4.0 and chef["reviews"] == 1 and chef["user_id"]
    listed = client.get(f"/api/v1/chefs/{pid}/reviews").json()
    assert listed[0]["customer_name"] == "Sneha P" and listed[0]["rating"] == 4
    assert client.get(B, headers=H(c)).json()[0]["reviewed"] is True
