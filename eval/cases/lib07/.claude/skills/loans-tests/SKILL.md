---
name: loans-tests
description: Guide for checking the library loans service. Use whenever loan or member behavior is added or changes.
---

# Loans tests

1. Use `fastapi.testclient.TestClient`; do not start a real server.
2. Put all tests in `tests/test_loans.py` and use a different member name in each test.
3. To test late fees pass `today` as a query parameter instead of waiting.
4. Run `pytest tests/test_loans.py` at the end and report the result.
