from models import Account


def account_summary_8(account: Account) -> str:
    """Summary of a account for report 8."""
    return f"Account {account.name} (tier {account.tier + 8}) {account.account_label()}"
