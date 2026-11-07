from models import Customer
from svc_8 import customer_summary_8


def test_summary_8():
    c = Customer("Ann", 2)
    assert customer_summary_8(c) == "Customer Ann (tier 10) Customer<Ann>"
