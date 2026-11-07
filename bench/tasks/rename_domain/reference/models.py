from dataclasses import dataclass


@dataclass
class Account:
    """A account of the shop."""
    name: str
    tier: int = 1

    def account_label(self) -> str:
        return f"Account<{self.name}>"
