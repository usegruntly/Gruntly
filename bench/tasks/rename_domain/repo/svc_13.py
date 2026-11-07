from models import Customer


def customer_summary_13(customer: Customer) -> str:
    """Summary of a customer for report 13."""
    return f"Customer {customer.name} (tier {customer.tier + 13}) {customer.customer_label()}"
