from models import Account
from svc_12 import account_summary_12


def test_summary_12():
    c = Account("Ann", 2)
    assert account_summary_12(c) == "Account Ann (tier 14) Account<Ann>"
