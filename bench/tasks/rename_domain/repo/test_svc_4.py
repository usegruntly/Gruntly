from models import Customer
from svc_4 import customer_summary_4


def test_summary_4():
    c = Customer("Ann", 2)
    assert customer_summary_4(c) == "Customer Ann (tier 6) Customer<Ann>"
