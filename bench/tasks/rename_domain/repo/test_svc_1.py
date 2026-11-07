from models import Customer
from svc_1 import customer_summary_1


def test_summary_1():
    c = Customer("Ann", 2)
    assert customer_summary_1(c) == "Customer Ann (tier 3) Customer<Ann>"
