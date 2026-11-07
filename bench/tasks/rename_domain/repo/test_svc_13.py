from models import Customer
from svc_13 import customer_summary_13


def test_summary_13():
    c = Customer("Ann", 2)
    assert customer_summary_13(c) == "Customer Ann (tier 15) Customer<Ann>"
