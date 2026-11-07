from models import Customer
from svc_11 import customer_summary_11


def test_summary_11():
    c = Customer("Ann", 2)
    assert customer_summary_11(c) == "Customer Ann (tier 13) Customer<Ann>"
