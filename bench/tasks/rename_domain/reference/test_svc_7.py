from models import Account
from svc_7 import account_summary_7


def test_summary_7():
    c = Account("Ann", 2)
    assert account_summary_7(c) == "Account Ann (tier 9) Account<Ann>"
