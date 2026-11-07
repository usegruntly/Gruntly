from models import Customer


def customer_summary_9(customer: Customer) -> str:
    """Summary of a customer for report 9."""
    return f"Customer {customer.name} (tier {customer.tier + 9}) {customer.customer_label()}"
