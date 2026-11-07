from models import Customer
from svc_6 import customer_summary_6


def test_summary_6():
    c = Customer("Ann", 2)
    assert customer_summary_6(c) == "Customer Ann (tier 8) Customer<Ann>"
