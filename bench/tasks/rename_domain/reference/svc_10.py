from models import Account


def account_summary_10(account: Account) -> str:
    """Summary of a account for report 10."""
    return f"Account {account.name} (tier {account.tier + 10}) {account.account_label()}"
