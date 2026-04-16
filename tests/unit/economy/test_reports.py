"""Testes das funções de relatórios financeiros — matemática pura."""

import pytest

from economy.models import Account, BalanceSnapshot, Transaction
from economy.reports import (
    calculate_monthly_burn,
    calculate_runway,
    consolidated_balance,
    summarize_by_month,
)


def make_transaction(
    amount: float, date: str = "2026-01-15", account_id: str = "acc1"
) -> Transaction:
    return Transaction(
        account_id=account_id,
        date=date,
        description="Test",
        amount=amount,
        type="debit" if amount < 0 else "credit",
    )


def make_account(
    id: str = "acc1",
    entity: str = "personal",
    type: str = "checking",
    opening_balance: float = 0.0,
) -> Account:
    return Account(
        id=id,
        name="Test",
        type=type,
        entity=entity,
        opening_balance=opening_balance,
        opening_date="2026-01-01",
    )


class TestCalculateRunway:
    def test_negative_burn_returns_months(self):
        months = calculate_runway(total_balance=10_000, monthly_burn=-1_000)
        assert months == pytest.approx(10.0)

    def test_zero_burn_returns_none(self):
        assert calculate_runway(1000, 0) is None

    def test_positive_burn_returns_none(self):
        assert calculate_runway(1000, 500) is None

    def test_very_small_burn(self):
        months = calculate_runway(total_balance=100, monthly_burn=-0.01)
        assert months == pytest.approx(10_000.0)

    def test_zero_balance_zero_runway(self):
        months = calculate_runway(total_balance=0, monthly_burn=-1000)
        assert months == pytest.approx(0.0)

    def test_returns_float(self):
        result = calculate_runway(5000, -500)
        assert isinstance(result, float)


class TestCalculateMonthlyBurn:
    def test_empty_transactions_return_zero(self):
        assert calculate_monthly_burn([]) == 0.0

    def test_explicit_months_divides_total(self):
        txns = [make_transaction(-3000)]
        burn = calculate_monthly_burn(txns, months=3)
        assert burn == pytest.approx(-1000.0)

    def test_single_transaction_no_months_returns_total(self):
        txns = [make_transaction(-500)]
        burn = calculate_monthly_burn(txns)
        assert burn == pytest.approx(-500.0)

    def test_income_and_expense_netted(self):
        txns = [
            make_transaction(2000, date="2026-01-01"),
            make_transaction(-3000, date="2026-02-01"),
        ]
        burn = calculate_monthly_burn(txns, months=1)
        assert burn == pytest.approx(-1000.0)

    def test_positive_net_returns_positive(self):
        txns = [
            make_transaction(5000, date="2026-01-01"),
            make_transaction(-1000, date="2026-02-01"),
        ]
        burn = calculate_monthly_burn(txns, months=1)
        assert burn == pytest.approx(4000.0)

    def test_date_range_used_when_months_not_given(self):
        txns = [
            make_transaction(-3000, date="2026-01-01"),
            make_transaction(-3000, date="2026-07-01"),  # ~6 months apart
        ]
        burn = calculate_monthly_burn(txns)
        # total = -6000, span ≈ 181 days / 30 ≈ 6 months → ≈ -1000/month
        assert burn < 0
        assert abs(burn) < 1100  # sanity bound


class TestSummarizeByMonth:
    def test_single_month_income_only(self):
        txns = [make_transaction(1000, date="2026-01-10")]
        result = summarize_by_month(txns)
        assert "2026-01" in result
        assert result["2026-01"]["income"] == pytest.approx(1000.0)
        assert result["2026-01"]["expense"] == pytest.approx(0.0)
        assert result["2026-01"]["net"] == pytest.approx(1000.0)

    def test_single_month_expense_only(self):
        txns = [make_transaction(-500, date="2026-02-15")]
        result = summarize_by_month(txns)
        assert result["2026-02"]["expense"] == pytest.approx(-500.0)
        assert result["2026-02"]["income"] == pytest.approx(0.0)
        assert result["2026-02"]["net"] == pytest.approx(-500.0)

    def test_mixed_income_and_expense(self):
        txns = [
            make_transaction(2000, date="2026-03-01"),
            make_transaction(-800, date="2026-03-15"),
        ]
        result = summarize_by_month(txns)
        assert result["2026-03"]["income"] == pytest.approx(2000.0)
        assert result["2026-03"]["expense"] == pytest.approx(-800.0)
        assert result["2026-03"]["net"] == pytest.approx(1200.0)

    def test_multiple_months_sorted(self):
        txns = [
            make_transaction(-100, date="2026-03-01"),
            make_transaction(-100, date="2026-01-01"),
            make_transaction(-100, date="2026-02-01"),
        ]
        result = summarize_by_month(txns)
        keys = list(result.keys())
        assert keys == sorted(keys)

    def test_empty_returns_empty(self):
        assert summarize_by_month([]) == {}


class TestConsolidatedBalance:
    def test_single_personal_checking_account(self):
        acc = make_account(id="a1", entity="personal", type="checking")
        snap = BalanceSnapshot(account_id="a1", date="2026-01-01", balance=5000.0)
        result = consolidated_balance([acc], {"a1": snap})
        assert result["personal"]["checking"] == pytest.approx(5000.0)
        assert result["total"] == pytest.approx(5000.0)

    def test_uses_opening_balance_when_no_snapshot(self):
        acc = make_account(id="a1", entity="personal", type="checking", opening_balance=1234.0)
        result = consolidated_balance([acc], {})
        assert result["personal"]["checking"] == pytest.approx(1234.0)

    def test_personal_and_business_summed_separately(self):
        personal = make_account(id="p1", entity="personal", type="checking")
        business = make_account(id="b1", entity="business", type="checking")
        snap_p = BalanceSnapshot(account_id="p1", date="2026-01-01", balance=3000.0)
        snap_b = BalanceSnapshot(account_id="b1", date="2026-01-01", balance=7000.0)
        result = consolidated_balance([personal, business], {"p1": snap_p, "b1": snap_b})
        assert result["personal"]["total"] == pytest.approx(3000.0)
        assert result["business"]["total"] == pytest.approx(7000.0)
        assert result["total"] == pytest.approx(10_000.0)

    def test_empty_accounts(self):
        result = consolidated_balance([], {})
        assert result["total"] == pytest.approx(0.0)
