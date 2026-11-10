from . import store
from .models import Product


class Inventory:
    def __init__(self, path):
        self.path = path
        self.products = store.load(path)

    def add(self, name: str, quantity: int, price: float, reorder_level: int = 0) -> Product:
        if quantity < 0 or price < 0 or reorder_level < 0:
            raise ValueError("quantity, price and reorder level must not be negative")
        p = self.products.get(name)
        if p:
            p.quantity += quantity
            p.price = price
            p.reorder_level = reorder_level
        else:
            p = self.products[name] = Product(name, quantity, price, reorder_level)
        store.save(self.path, self.products)
        return p

    def remove(self, name: str, quantity: int) -> Product:
        p = self.products.get(name)
        if p is None:
            raise KeyError(name)
        if quantity > p.quantity:
            raise ValueError(f"only {p.quantity} {name} in stock")
        p.quantity -= quantity
        store.save(self.path, self.products)
        return p

    def total_value(self) -> float:
        return round(sum(p.quantity * p.price for p in self.products.values()), 2)

    def low_stock(self) -> list:
        return [p for _, p in sorted(self.products.items()) if p.low]

    def names(self) -> list:
        return sorted(self.products)
