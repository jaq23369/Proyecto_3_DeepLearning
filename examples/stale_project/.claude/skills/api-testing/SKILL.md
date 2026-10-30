---
name: api-testing
description: Write and update tests for the forecast API. Use for any change in the API.
---

# API testing

When an endpoint changes, add or update its tests.

1. Tests for the prediction endpoint live in `tests/test_predict.py`.
2. Every test must call `POST /predict` with a valid city and check the `prediction` list.
3. Use `fastapi.testclient.TestClient`, never start a real server.
4. Always run `pytest tests/` before finishing and paste the summary.
