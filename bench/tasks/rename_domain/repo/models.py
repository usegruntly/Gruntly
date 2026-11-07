from dataclasses import dataclass


@dataclass
class Customer:
    """A customer of the shop."""
    name: str
    tier: int = 1

    def customer_label(self) -> str:
        return f"Customer<{self.name}>"
