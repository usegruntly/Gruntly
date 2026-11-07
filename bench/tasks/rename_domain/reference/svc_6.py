from models import Account


def account_summary_6(account: Account) -> str:
    """Summary of a account for report 6."""
    return f"Account {account.name} (tier {account.tier + 6}) {account.account_label()}"
