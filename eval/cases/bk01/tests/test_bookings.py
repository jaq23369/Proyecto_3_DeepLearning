from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_too_many_guests():
    res = client.post(
        "/bookings",
        json={"room": "tikal", "guests": 9, "check_in": "2026-11-02", "check_out": "2026-11-03"},
    )
    assert res.status_code == 422


def test_cancel_keeps_booking():
    created = client.post(
        "/bookings",
        json={"room": "pacaya", "guests": 2, "check_in": "2026-11-02", "check_out": "2026-11-04"},
    ).json()
    client.post(f"/bookings/{created['id']}/cancel")
    assert client.get(f"/bookings/{created['id']}").json()["status"] == "cancelled"
