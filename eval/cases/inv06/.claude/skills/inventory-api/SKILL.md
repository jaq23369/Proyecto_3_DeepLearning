---
name: inventory-api
description: Add or change endpoints of the inventory API in app/routers/. Use when adding routes or changing request validation.
---

# Inventory API

1. Each resource has its own router in `app/routers/` with an `APIRouter` prefix.
2. Request and response models live in `app/models.py`.
3. Return 404 when a product does not exist and 409 when stock would go below zero.
4. After changing a route, update the endpoint table in `README.md`.
5. Run the whole test suite with pytest before you finish.
