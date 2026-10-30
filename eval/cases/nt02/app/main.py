from fastapi import FastAPI

from app.api import notes

app = FastAPI(title="Notes API")
app.include_router(notes.router, prefix="/v1")
