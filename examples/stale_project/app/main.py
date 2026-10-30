from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.model import forecast_city, known_cities

app = FastAPI(title="Weather Forecast API")

DEFAULT_DAYS = 3


class ForecastRequest(BaseModel):
    city: str
    days: int = Field(default=DEFAULT_DAYS, ge=1, le=7)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/cities")
def cities():
    return {"cities": known_cities()}


@app.post("/forecast")
def forecast(req: ForecastRequest):
    temps = forecast_city(req.city, req.days)
    return {"city": req.city, "forecast": temps}
