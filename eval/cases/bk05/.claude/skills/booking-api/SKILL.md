---
name: booking-api
description: Change booking endpoints or booking validation rules. Use when editing app/main.py, app/models.py or app/config.py.
---

# Booking API

1. Validation rules live in `app/models.py`; limits such as guests and nights come from `app/config.py`.
2. Keep cancelled bookings in memory with status `cancelled` instead of deleting them.
3. Every new rule needs a test in `tests/test_bookings.py`.
