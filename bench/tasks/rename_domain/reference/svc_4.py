from models import Account


def account_summary_4(account: Account) -> str:
    """Summary of a account for report 4."""
    return f"Account {account.name} (tier {account.tier + 4}) {account.account_label()}"
