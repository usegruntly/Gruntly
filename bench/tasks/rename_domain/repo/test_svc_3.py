from models import Customer
from svc_3 import customer_summary_3


def test_summary_3():
    c = Customer("Ann", 2)
    assert customer_summary_3(c) == "Customer Ann (tier 5) Customer<Ann>"
