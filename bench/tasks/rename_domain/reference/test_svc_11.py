from models import Account
from svc_11 import account_summary_11


def test_summary_11():
    c = Account("Ann", 2)
    assert account_summary_11(c) == "Account Ann (tier 13) Account<Ann>"
