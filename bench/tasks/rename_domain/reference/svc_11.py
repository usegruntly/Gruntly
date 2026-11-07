from models import Account


def account_summary_11(account: Account) -> str:
    """Summary of a account for report 11."""
    return f"Account {account.name} (tier {account.tier + 11}) {account.account_label()}"
