from models import Account
from svc_4 import account_summary_4


def test_summary_4():
    c = Account("Ann", 2)
    assert account_summary_4(c) == "Account Ann (tier 6) Account<Ann>"
