from fastapi.testclient import TestClient

from helpdesk.main import app

client = TestClient(app)


def make(title: str, priority: str = "medium"):
    return client.post("/api/tickets", json={"title": title, "priority": priority})


def test_title_too_long():
    assert make("x" * 81).status_code == 422


def test_unknown_priority():
    assert make("printer is down", "urgent").status_code == 422


def test_close_ticket():
    ticket = make("vpn drops").json()
    closed = client.post(f"/api/tickets/{ticket['id']}/resolve").json()
    assert closed["status"] == "closed"


def test_filter_by_status():
    ticket = make("new laptop").json()
    client.post(f"/api/tickets/{ticket['id']}/resolve")
    open_ids = [t["id"] for t in client.get("/api/tickets", params={"status": "open"}).json()]
    assert ticket["id"] not in open_ids
