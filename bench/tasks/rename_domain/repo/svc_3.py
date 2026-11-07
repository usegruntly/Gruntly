from models import Customer


def customer_summary_3(customer: Customer) -> str:
    """Summary of a customer for report 3."""
    return f"Customer {customer.name} (tier {customer.tier + 3}) {customer.customer_label()}"
