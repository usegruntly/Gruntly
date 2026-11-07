from models import Account
from svc_9 import account_summary_9


def test_summary_9():
    c = Account("Ann", 2)
    assert account_summary_9(c) == "Account Ann (tier 11) Account<Ann>"
