from models import Account
from svc_1 import account_summary_1


def test_summary_1():
    c = Account("Ann", 2)
    assert account_summary_1(c) == "Account Ann (tier 3) Account<Ann>"
