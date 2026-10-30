from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def lend(member: str, book_id: int):
    return client.post("/loans", json={"member": member, "book_id": book_id})


def test_loan_limit():
    for _ in range(3):
        assert lend("ana", 1).status_code == 201
    assert lend("ana", 1).status_code == 409


def test_no_copies_left():
    assert lend("bea", 2).status_code == 201
    assert lend("carl", 2).status_code == 409


def test_late_return_fine():
    loan = lend("dani", 3).json()
    today = date.fromisoformat(loan["due"]) + timedelta(days=2)
    res = client.post(f"/loans/{loan['id']}/return", params={"today": today.isoformat()})
    assert res.json()["fine"] == 1.0


def test_member_history():
    lend("eli", 3)
    assert len(client.get("/members/eli/history").json()) == 1
