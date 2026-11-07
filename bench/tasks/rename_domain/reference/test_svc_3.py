from models import Account
from svc_3 import account_summary_3


def test_summary_3():
    c = Account("Ann", 2)
    assert account_summary_3(c) == "Account Ann (tier 5) Account<Ann>"
