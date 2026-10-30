from fastapi import FastAPI

from app.routers import products

app = FastAPI(title="Inventory Service")
app.include_router(products.router)
