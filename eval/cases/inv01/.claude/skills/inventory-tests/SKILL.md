---
name: inventory-tests
description: Write or fix pytest tests for the inventory API. Use when a test fails or a new test is needed in tests/.
---

# Inventory tests

1. Use `fastapi.testclient.TestClient`; do not start a real server.
2. Load sample data with `python -m app.fixtures` or by calling `load()` from `app/fixtures.py`.
3. Put tests for product routes in `tests/test_products.py`.
4. Always run `pytest` at the end and report the result.
