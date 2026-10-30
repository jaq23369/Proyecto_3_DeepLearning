# Notes API

Personal notes service with search. FastAPI and in-memory storage.

## Usage

```bash
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

All routes are under the `/v1` prefix.

- `GET /v1/notes` returns your notes, newest first.
- `POST /v1/notes` creates a note with `title` and `body`.
- `DELETE /v1/notes/{note_id}` deletes a note and returns status 204 with an empty body.
- `GET /v1/notes/search?q=word` finds notes whose title or body contains the word.

See `CHANGELOG.md` for the release history.
