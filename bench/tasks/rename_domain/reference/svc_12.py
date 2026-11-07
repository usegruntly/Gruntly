from models import Account


def account_summary_12(account: Account) -> str:
    """Summary of a account for report 12."""
    return f"Account {account.name} (tier {account.tier + 12}) {account.account_label()}"
