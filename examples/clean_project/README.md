# Task Board API

Small FastAPI service to keep a list of tasks.

## Requirements

- Python 3.12 or newer
- Dependencies in `requirements.txt`

## Run locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Endpoints

### `GET /health`

Returns `{"status": "ok"}`.

### `GET /tasks`

Returns all tasks, newest first.

### `POST /tasks`

Request body:

```json
{"title": "Buy milk", "priority": "high"}
```

Response (status 201):

```json
{"id": 1, "title": "Buy milk", "priority": "high", "done": false}
```

`priority` is `low`, `normal` or `high` and defaults to `normal`.

### `POST /tasks/{task_id}/done`

Marks a task as done and returns it. Answers 404 if the task does not exist.

## Tests

```bash
pytest tests/test_api.py
```
