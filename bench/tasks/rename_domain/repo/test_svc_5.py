from models import Customer
from svc_5 import customer_summary_5


def test_summary_5():
    c = Customer("Ann", 2)
    assert customer_summary_5(c) == "Customer Ann (tier 7) Customer<Ann>"
