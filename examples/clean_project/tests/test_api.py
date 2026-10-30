from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_create_task_defaults_to_normal_priority():
    res = client.post("/tasks", json={"title": "Buy milk"})
    assert res.status_code == 201
    assert res.json()["priority"] == "normal"


def test_list_is_newest_first():
    client.post("/tasks", json={"title": "first"})
    last = client.post("/tasks", json={"title": "second"}).json()
    assert client.get("/tasks").json()[0]["id"] == last["id"]


def test_done_unknown_task():
    assert client.post("/tasks/9999/done").status_code == 404
