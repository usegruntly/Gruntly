from models import Customer


def customer_summary_5(customer: Customer) -> str:
    """Summary of a customer for report 5."""
    return f"Customer {customer.name} (tier {customer.tier + 5}) {customer.customer_label()}"
