# Helpdesk Tickets API

Track support tickets. FastAPI and in-memory storage.

## Usage

```bash
pip install -r requirements.txt
uvicorn helpdesk.main:app --port 8000
```

Every route lives under the `/api` prefix.

- `POST /api/tickets` creates a ticket with `title` and `priority`.
- `GET /api/tickets?status=open` lists tickets, filtered by `status` when it is given.
- `POST /api/tickets/{ticket_id}/close` closes a ticket and returns it with status `closed`.
- `PATCH /api/tickets/{ticket_id}/priority` changes the priority to `low`, `normal` or `high`.

The title can have at most 80 characters. Set `HELPDESK_MAX_TITLE` to change that limit.

## Tests

```bash
pytest tests/test_tickets.py
```

Release history is kept in `CHANGES.md`.
