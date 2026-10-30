---
name: task-api
description: Add or change endpoints of the task board API. Use when editing app/main.py or app/schemas.py.
---

# Task API

1. Request models live in `app/schemas.py` and use Pydantic.
2. Tasks are kept in `app/store.py`; routes never touch the task dictionary directly.
3. Return 404 when a task does not exist.
4. After changing a route, update the endpoint list in `README.md`.
