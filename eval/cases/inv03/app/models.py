from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    sku: str
    name: str
    price: float = Field(gt=0)
    stock: int = Field(default=0, ge=0)


class Product(ProductCreate):
    id: int


class StockChange(BaseModel):
    change: int
