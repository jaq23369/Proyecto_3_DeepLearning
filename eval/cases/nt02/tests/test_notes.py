from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_search_ignores_case():
    client.post("/v1/notes", json={"title": "Groceries", "body": "Buy MILK"})
    found = client.get("/v1/notes/find", params={"q": "milk"}).json()
    assert len(found) == 1


def test_delete_returns_204():
    note = client.post("/v1/notes", json={"title": "tmp", "body": "x"}).json()
    assert client.delete(f"/v1/notes/{note['id']}").status_code == 204
