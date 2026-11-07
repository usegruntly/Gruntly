from models import Account


def account_summary_1(account: Account) -> str:
    """Summary of a account for report 1."""
    return f"Account {account.name} (tier {account.tier + 1}) {account.account_label()}"
