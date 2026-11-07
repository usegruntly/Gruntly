from models import Customer
from svc_10 import customer_summary_10


def test_summary_10():
    c = Customer("Ann", 2)
    assert customer_summary_10(c) == "Customer Ann (tier 12) Customer<Ann>"
