"""Financial reports: runway, burn rate, consolidated view."""

from datetime import datetime

from economy.models import Account, BalanceSnapshot, Transaction


def calculate_runway(
    total_balance: float,
    monthly_burn: float,
) -> float | None:
    """Calculate runway in months. Returns None if burn is zero or positive."""
    if monthly_burn >= 0:
        return None  # no burn = infinite runway
    return total_balance / abs(monthly_burn)


def calculate_monthly_burn(
    transactions: list[Transaction],
    months: int | None = None,
) -> float:
    """Calculate average monthly burn (net outflow) from transactions.

    Returns negative number if spending exceeds income.
    """
    if not transactions:
        return 0.0

    total = sum(t.amount for t in transactions)

    if months:
        return total / months

    # Calculate months from date range
    dates = sorted(t.date for t in transactions)
    if len(dates) < 2:
        return total

    start = datetime.fromisoformat(dates[0])
    end = datetime.fromisoformat(dates[-1])
    delta_months = max((end - start).days / 30.0, 1.0)
    return total / delta_months


def summarize_by_month(transactions: list[Transaction]) -> dict[str, dict]:
    """Group transactions by month with income/expense/net totals.

    Returns dict like: {"2026-01": {"income": 800.0, "expense": -821.49, "net": -21.49}}
    """
    months: dict[str, dict] = {}
    for t in transactions:
        month_key = t.date[:7]  # YYYY-MM
        if month_key not in months:
            months[month_key] = {"income": 0.0, "expense": 0.0, "net": 0.0}
        if t.amount >= 0:
            months[month_key]["income"] += t.amount
        else:
            months[month_key]["expense"] += t.amount
        months[month_key]["net"] += t.amount
    return dict(sorted(months.items()))


def consolidated_balance(accounts: list[Account], snapshots: dict[str, BalanceSnapshot]) -> dict:
    """Calculate consolidated balance across all accounts.

    Args:
        accounts: list of accounts
        snapshots: dict of account_id -> latest BalanceSnapshot

    Returns dict with personal/business/total balances.
    """
    result = {
        "personal": {"checking": 0.0, "credit_card": 0.0, "total": 0.0},
        "business": {"checking": 0.0, "credit_card": 0.0, "total": 0.0},
        "total": 0.0,
    }

    for acc in accounts:
        snap = snapshots.get(acc.id)
        balance = snap.balance if snap else acc.opening_balance
        entity_key = acc.entity
        result[entity_key][acc.type] += balance
        result[entity_key]["total"] += balance
        result["total"] += balance

    return result
