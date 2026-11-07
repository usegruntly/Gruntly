from models import Account
from svc_5 import account_summary_5


def test_summary_5():
    c = Account("Ann", 2)
    assert account_summary_5(c) == "Account Ann (tier 7) Account<Ann>"
