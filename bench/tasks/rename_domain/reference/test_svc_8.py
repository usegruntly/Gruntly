from models import Account
from svc_8 import account_summary_8


def test_summary_8():
    c = Account("Ann", 2)
    assert account_summary_8(c) == "Account Ann (tier 10) Account<Ann>"
