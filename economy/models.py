"""Pydantic models for economy tracking."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class Account(BaseModel):
    id: str = Field(default_factory=lambda: _uuid())
    name: str
    bank: str | None = None
    agency: str | None = None
    account_number: str | None = None
    type: str  # 'checking', 'credit_card'
    entity: str  # 'personal', 'business'
    opening_balance: float = 0.0
    opening_date: str  # ISO date (YYYY-MM-DD)
    created_at: str = Field(default_factory=lambda: _now())
    metadata: str | None = None


class Category(BaseModel):
    id: str = Field(default_factory=lambda: _uuid())
    name: str
    type: str  # 'income', 'expense', 'transfer'
    created_at: str = Field(default_factory=lambda: _now())


class Transaction(BaseModel):
    id: str = Field(default_factory=lambda: _uuid())
    account_id: str
    date: str  # ISO date (YYYY-MM-DD)
    description: str
    memo: str | None = None
    amount: float  # positive = credit, negative = debit
    type: str  # 'credit', 'debit'
    category_id: str | None = None
    fit_id: str | None = None  # bank's transaction ID for dedup
    balance_after: float | None = None
    created_at: str = Field(default_factory=lambda: _now())
    metadata: str | None = None


class BalanceSnapshot(BaseModel):
    id: str = Field(default_factory=lambda: _uuid())
    account_id: str
    date: str  # ISO date (YYYY-MM-DD)
    balance: float
    source: str = "manual"  # 'manual', 'ofx', 'reconciliation'
    created_at: str = Field(default_factory=lambda: _now())


def _uuid() -> str:
    import uuid

    return uuid.uuid4().hex[:8]


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
