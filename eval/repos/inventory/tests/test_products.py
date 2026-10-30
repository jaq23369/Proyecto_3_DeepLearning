from fastapi.testclient import TestClient

from app.fixtures import load
from app.main import app

client = TestClient(app)
load()


def test_list_products():
    assert len(client.get("/products/").json()) >= 2


def test_stock_cannot_go_negative():
    res = client.patch("/products/1/stock", json={"delta": -999})
    assert res.status_code == 409
