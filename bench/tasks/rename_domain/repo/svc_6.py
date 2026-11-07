from models import Customer


def customer_summary_6(customer: Customer) -> str:
    """Summary of a customer for report 6."""
    return f"Customer {customer.name} (tier {customer.tier + 6}) {customer.customer_label()}"
