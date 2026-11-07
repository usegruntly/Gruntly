from models import Account
from svc_10 import account_summary_10


def test_summary_10():
    c = Account("Ann", 2)
    assert account_summary_10(c) == "Account Ann (tier 12) Account<Ann>"
