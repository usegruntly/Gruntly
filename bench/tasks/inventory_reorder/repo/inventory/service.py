from . import store
from .models import Product


class Inventory:
    def __init__(self, path):
        self.path = path
        self.products = store.load(path)

    def add(self, name: str, quantity: int, price: float) -> Product:
        if quantity < 0 or price < 0:
            raise ValueError("quantity and price must not be negative")
        p = self.products.get(name)
        if p:
            p.quantity += quantity
            p.price = price
        else:
            p = self.products[name] = Product(name, quantity, price)
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

    def names(self) -> list:
        return sorted(self.products)
