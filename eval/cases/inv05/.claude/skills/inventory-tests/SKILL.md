---
name: inventory-tests
description: Testing guide for the inventory service. Use whenever the inventory API is modified.
---

# Inventory tests

1. Use `fastapi.testclient.TestClient`; do not start a real server.
2. Load sample data with `python -m app.fixtures` or by calling `load()` from `app/fixtures.py`.
3. Put tests for product routes in `tests/test_products.py`.
4. Always run `pytest` at the end and report the result.
