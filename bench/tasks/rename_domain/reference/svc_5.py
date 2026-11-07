from models import Account


def account_summary_5(account: Account) -> str:
    """Summary of a account for report 5."""
    return f"Account {account.name} (tier {account.tier + 5}) {account.account_label()}"
