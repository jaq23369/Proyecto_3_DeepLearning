from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_forecast_days():
    res = client.post("/forecast", json={"city": "Guatemala", "days": 2})
    assert res.status_code == 200
    assert len(res.json()["forecast"]) == 2
