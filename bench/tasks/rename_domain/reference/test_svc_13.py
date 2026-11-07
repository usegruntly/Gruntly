from models import Account
from svc_13 import account_summary_13


def test_summary_13():
    c = Account("Ann", 2)
    assert account_summary_13(c) == "Account Ann (tier 15) Account<Ann>"
