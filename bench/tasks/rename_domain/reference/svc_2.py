from models import Account


def account_summary_2(account: Account) -> str:
    """Summary of a account for report 2."""
    return f"Account {account.name} (tier {account.tier + 2}) {account.account_label()}"
