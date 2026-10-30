---
name: api-changes
description: Guide for modifying endpoints of the forecast API. Use for any change in the API.
---

# Changing the API

1. Keep request models in `app/main.py` using Pydantic.
2. Validate `days` between 1 and 7.
3. Update the endpoint list in `README.md` when a route changes.
4. Always run `pytest tests/` before finishing and paste the summary.
