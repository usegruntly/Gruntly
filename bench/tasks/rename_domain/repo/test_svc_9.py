from models import Customer
from svc_9 import customer_summary_9


def test_summary_9():
    c = Customer("Ann", 2)
    assert customer_summary_9(c) == "Customer Ann (tier 11) Customer<Ann>"
