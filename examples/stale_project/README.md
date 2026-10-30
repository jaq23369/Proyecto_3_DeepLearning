# Weather Forecast API

Small FastAPI service that returns a temperature forecast for a city.

## Requirements

- Python 3.11 or newer
- Dependencies in `requirements.txt`

## Run locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Settings such as the default number of days live in `config/settings.yaml`.

## Endpoints

### `POST /predict`

Request body:

```json
{"city": "Guatemala", "days": 3}
```

Response:

```json
{"city": "Guatemala", "prediction": [24.1, 23.8, 25.0]}
```

### `GET /health`

Returns `{"status": "ok"}`.

## Tests

```bash
pytest tests/test_api.py
```
