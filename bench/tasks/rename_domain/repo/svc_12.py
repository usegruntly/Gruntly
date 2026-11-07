from models import Customer


def customer_summary_12(customer: Customer) -> str:
    """Summary of a customer for report 12."""
    return f"Customer {customer.name} (tier {customer.tier + 12}) {customer.customer_label()}"
