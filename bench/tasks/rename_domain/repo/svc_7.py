from models import Customer


def customer_summary_7(customer: Customer) -> str:
    """Summary of a customer for report 7."""
    return f"Customer {customer.name} (tier {customer.tier + 7}) {customer.customer_label()}"
