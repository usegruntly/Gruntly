from models import Account


def account_summary_7(account: Account) -> str:
    """Summary of a account for report 7."""
    return f"Account {account.name} (tier {account.tier + 7}) {account.account_label()}"
