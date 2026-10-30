---
name: loans-api
description: Change loan endpoints or loan rules. Use when editing app/main.py, app/models.py or app/config.py.
---

# Loans API

1. Limits such as loan days, loan count and the late fee live in `app/config.py`; never hard-code them.
2. Return 409 when a book has no copies left or when a member reached the loan limit.
3. Request and response models live in `app/models.py`.
4. After changing a route, update the endpoint table in `README.md`.
5. Before you finish, run the loan tests with pytest and report what happened.
