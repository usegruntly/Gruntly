from models import Customer


def customer_summary_8(customer: Customer) -> str:
    """Summary of a customer for report 8."""
    return f"Customer {customer.name} (tier {customer.tier + 8}) {customer.customer_label()}"
