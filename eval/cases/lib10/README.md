# Library Loans API

Lend books to members. Built with FastAPI and in-memory storage.

## Run

```bash
pip install -r requirements.txt
uvicorn app.main:app
```

## Rules

- A loan lasts 14 days.
- A member can have at most 3 active loans.
- A late return costs 0.50 per day.

## Endpoints

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/books` | List books and their free copies. |
| POST | `/loans` | Lend a book to a member. |
| POST | `/loans/{loan_id}/return` | Return a book and get the late fee. |
| GET | `/members/{member}/loans` | List the loans of a member. |

Example body for `POST /loans`:

```json
{"member": "ana", "book_id": 1}
```

## Tests

```bash
pytest tests/test_loans.py
```
