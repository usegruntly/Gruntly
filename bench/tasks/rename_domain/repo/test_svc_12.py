from models import Customer
from svc_12 import customer_summary_12


def test_summary_12():
    c = Customer("Ann", 2)
    assert customer_summary_12(c) == "Customer Ann (tier 14) Customer<Ann>"
