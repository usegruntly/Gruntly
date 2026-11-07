from models import Customer


def customer_summary_2(customer: Customer) -> str:
    """Summary of a customer for report 2."""
    return f"Customer {customer.name} (tier {customer.tier + 2}) {customer.customer_label()}"
