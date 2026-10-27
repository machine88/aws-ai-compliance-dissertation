"""Deterministic estimates for explicitly assumed baseline usage, not billing forecasts."""
from decimal import Decimal, InvalidOperation


def estimate_cost(usage, rates):
    """Multiply named nonnegative usage by matching rates and return auditable costs.

    Inputs:
        usage: Named nonnegative usage quantities.
        rates: Matching per-unit USD prices.

    Outputs:
        dict: Auditable per-category costs and exact total expressed as decimal strings.
    """
    if set(usage) != set(rates):
        raise ValueError("Usage must match every rate key; missing costs are not zero")
    costs = {}
    # Use named quantities and Decimal arithmetic to avoid hidden categories or floating-point cost errors.
    for name, quantity in usage.items():
        try:
            quantity = Decimal(str(quantity))
            rate = Decimal(str(rates[name]["usd_per_unit"]))
        except (InvalidOperation, KeyError) as error:
            raise ValueError(f"Invalid quantity or rate for {name}") from error
        if not quantity.is_finite() or not rate.is_finite() or quantity < 0 or rate < 0:
            raise ValueError("Quantities and prices must be finite and nonnegative")
        costs[name] = str(quantity * rate)
    return {"line_items_usd": costs, "total_usd": str(sum(map(Decimal, costs.values()), Decimal(0)))}
