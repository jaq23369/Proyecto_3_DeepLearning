from fastapi import FastAPI

from helpdesk import routes

app = FastAPI(title="Helpdesk Tickets API")
app.include_router(routes.router, prefix="/api")
