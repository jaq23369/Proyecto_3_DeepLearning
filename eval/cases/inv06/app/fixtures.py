from app.models import Product
from app.store import STORE

SAMPLE = [
    Product(id=1, sku="TB-001", name="Toolbox", price=35.0, stock=12),
    Product(id=2, sku="HM-002", name="Hammer", price=12.5, stock=40),
]


def load() -> None:
    for product in SAMPLE:
        STORE[product.id] = product


if __name__ == "__main__":
    load()
    print(f"Loaded {len(SAMPLE)} products")
