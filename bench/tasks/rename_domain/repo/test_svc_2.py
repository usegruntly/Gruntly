from models import Customer
from svc_2 import customer_summary_2


def test_summary_2():
    c = Customer("Ann", 2)
    assert customer_summary_2(c) == "Customer Ann (tier 4) Customer<Ann>"
