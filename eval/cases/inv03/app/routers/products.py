from fastapi import APIRouter, HTTPException

from app.models import Product, ProductCreate, StockChange
from app.store import STORE

router = APIRouter(prefix="/products", tags=["products"])


@router.get("/")
def list_products() -> list[Product]:
    return list(STORE.values())


@router.get("/{product_id}")
def get_product(product_id: int) -> Product:
    if product_id not in STORE:
        raise HTTPException(status_code=404, detail="Product not found")
    return STORE[product_id]


@router.post("/", status_code=201)
def create_product(data: ProductCreate) -> Product:
    product_id = max(STORE, default=0) + 1
    product = Product(id=product_id, **data.model_dump())
    STORE[product_id] = product
    return product


@router.patch("/{product_id}/stock")
def change_stock(product_id: int, body: StockChange) -> Product:
    product = get_product(product_id)
    new_stock = product.stock + body.change
    if new_stock < 0:
        raise HTTPException(status_code=409, detail="Stock cannot go below zero")
    product.stock = new_stock
    return product
