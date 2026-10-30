# Inventory Service

REST API to keep track of product stock in a small warehouse.

## Setup

```bash
pip install -r requirements.txt
python -m app.seed_data
uvicorn app.main:app --reload
```

`python -m app.seed_data` loads a few sample products into memory.

## Endpoints

| Method | Path | Description |
| --- | --- | --- |
| GET | `/products` | List all products |
| GET | `/products/{product_id}` | Get one product |
| POST | `/products` | Create a product |
| PATCH | `/products/{product_id}/stock` | Add or remove units |

To change stock send a JSON body like `{"delta": -3}`. Stock can never go below zero; the API answers 409 if it would.

## Tests

```bash
pytest
```
