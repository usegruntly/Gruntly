from models import Customer


def customer_summary_11(customer: Customer) -> str:
    """Summary of a customer for report 11."""
    return f"Customer {customer.name} (tier {customer.tier + 11}) {customer.customer_label()}"
