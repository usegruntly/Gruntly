from models import Account
from svc_6 import account_summary_6


def test_summary_6():
    c = Account("Ann", 2)
    assert account_summary_6(c) == "Account Ann (tier 8) Account<Ann>"
