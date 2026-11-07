from models import Customer


def customer_summary_1(customer: Customer) -> str:
    """Summary of a customer for report 1."""
    return f"Customer {customer.name} (tier {customer.tier + 1}) {customer.customer_label()}"
