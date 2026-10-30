from fastapi import FastAPI, HTTPException

from app.config import ROOMS
from app.schemas import Booking, BookingCreate

app = FastAPI(title="Room Booking API")
BOOKINGS: dict[int, Booking] = {}


@app.get("/rooms")
def list_rooms():
    return ROOMS


@app.post("/bookings", status_code=201)
def create_booking(data: BookingCreate) -> Booking:
    if data.room not in ROOMS:
        raise HTTPException(status_code=404, detail="Unknown room")
    booking = Booking(id=len(BOOKINGS) + 1, status="active", **data.model_dump())
    BOOKINGS[booking.id] = booking
    return booking


@app.get("/bookings/{booking_id}")
def get_booking(booking_id: int) -> Booking:
    if booking_id not in BOOKINGS:
        raise HTTPException(status_code=404, detail="Booking not found")
    return BOOKINGS[booking_id]


@app.post("/bookings/{booking_id}/cancel")
def cancel_booking(booking_id: int) -> Booking:
    booking = get_booking(booking_id)
    booking.status = "cancelled"
    return booking
