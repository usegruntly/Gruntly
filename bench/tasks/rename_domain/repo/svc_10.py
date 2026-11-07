from models import Customer


def customer_summary_10(customer: Customer) -> str:
    """Summary of a customer for report 10."""
    return f"Customer {customer.name} (tier {customer.tier + 10}) {customer.customer_label()}"
