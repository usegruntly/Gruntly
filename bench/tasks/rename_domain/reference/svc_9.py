from models import Account


def account_summary_9(account: Account) -> str:
    """Summary of a account for report 9."""
    return f"Account {account.name} (tier {account.tier + 9}) {account.account_label()}"
