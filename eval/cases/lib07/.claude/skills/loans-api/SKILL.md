---
name: loans-api
description: Guide for working on the library loans service. Use whenever a loan, book or member behavior has to change.
---

# Loans API

1. Limits such as loan days, loan count and the late fee live in `app/config.py`; never hard-code them.
2. Return 409 when a book has no copies left or when a member reached the loan limit.
3. Request and response models live in `app/models.py`.
4. After changing a route, update the endpoint table in `README.md`.
