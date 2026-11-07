from models import Account
from svc_2 import account_summary_2


def test_summary_2():
    c = Account("Ann", 2)
    assert account_summary_2(c) == "Account Ann (tier 4) Account<Ann>"
