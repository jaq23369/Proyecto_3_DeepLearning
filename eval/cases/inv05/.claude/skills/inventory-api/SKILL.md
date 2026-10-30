---
name: inventory-api
description: Guide for the inventory API. Use when changing anything in the inventory API.
---

# Inventory API

1. Each resource has its own router in `app/routers/` with an `APIRouter` prefix.
2. Request and response models live in `app/models.py`.
3. Return 404 when a product does not exist and 409 when stock would go below zero.
4. After changing a route, update the endpoint table in `README.md`.
