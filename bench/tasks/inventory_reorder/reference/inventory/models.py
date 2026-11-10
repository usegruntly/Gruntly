from dataclasses import dataclass


@dataclass
class Product:
    name: str
    quantity: int
    price: float
    reorder_level: int = 0

    @property
    def low(self) -> bool:
        return self.quantity <= self.reorder_level
