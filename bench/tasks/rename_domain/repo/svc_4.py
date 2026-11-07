from models import Customer


def customer_summary_4(customer: Customer) -> str:
    """Summary of a customer for report 4."""
    return f"Customer {customer.name} (tier {customer.tier + 4}) {customer.customer_label()}"
