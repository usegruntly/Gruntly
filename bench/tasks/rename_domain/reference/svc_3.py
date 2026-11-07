from models import Account


def account_summary_3(account: Account) -> str:
    """Summary of a account for report 3."""
    return f"Account {account.name} (tier {account.tier + 3}) {account.account_label()}"
