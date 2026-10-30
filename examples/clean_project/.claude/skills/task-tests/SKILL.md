---
name: task-tests
description: Write or fix pytest tests for the task board API. Use when a test fails or a new test is needed in tests/.
---

# Task tests

1. Use `fastapi.testclient.TestClient`; do not start a real server.
2. Put the tests in `tests/test_api.py`.
3. Run `pytest tests/test_api.py` at the end and report the result.
