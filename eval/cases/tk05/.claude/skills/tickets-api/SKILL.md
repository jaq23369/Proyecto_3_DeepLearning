---
name: tickets-api
description: Modify the ticket endpoints in helpdesk/routes.py. Use when adding, changing or removing a ticket route.
---

# Tickets API

1. Routes go in `helpdesk/routes.py`; the `/api` prefix is added in `helpdesk/main.py`.
2. Valid priorities are listed in `PRIORITIES` in `helpdesk/config.py`; reject any other value with 422.
3. Closing a ticket sets its status to `closed` and never deletes it.
4. Add a test in `tests/test_tickets.py` for every new route.
