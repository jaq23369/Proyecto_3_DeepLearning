# Room Booking API

Book meeting rooms by the day. Built with FastAPI.

## Run

```bash
pip install -r requirements.txt
uvicorn app.main:app
```

## Rules

- A booking needs between 1 and 4 guests.
- `check_out` must be after `check_in`.
- A booking can last at most 14 nights.

## Endpoints

- `GET /rooms`: list rooms and their capacity.
- `POST /bookings`: create a booking.
- `GET /bookings/{booking_id}`: read a booking.
- `POST /bookings/{booking_id}/cancel`: cancel a booking. Cancelled bookings are kept with status `cancelled`.

## Tests

```bash
pytest tests/test_bookings.py
```
