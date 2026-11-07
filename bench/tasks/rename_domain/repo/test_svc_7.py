from models import Customer
from svc_7 import customer_summary_7


def test_summary_7():
    c = Customer("Ann", 2)
    assert customer_summary_7(c) == "Customer Ann (tier 9) Customer<Ann>"
