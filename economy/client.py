"""EconomyClient — high-level API for personal finance tracking."""

import sqlite3
from pathlib import Path

from economy.db import ensure_schema, get_connection
from economy.importers.itau_csv_parser import parse_itau_cc_csv
from economy.importers.ofx_parser import parse_ofx
from economy.models import Account, BalanceSnapshot, Transaction
from economy.reports import (
    calculate_monthly_burn,
    calculate_runway,
    consolidated_balance,
    summarize_by_month,
)
from economy.store import EconomyStore


class EconomyClient:
    def __init__(self, conn: sqlite3.Connection | None = None, db_path: Path | None = None):
        if conn:
            self.conn = conn
            ensure_schema(self.conn)
        else:
            self.conn = get_connection(db_path)
        self.store = EconomyStore(self.conn)

    # --- Accounts ---

    def add_account(
        self,
        name: str,
        type: str,
        entity: str,
        opening_balance: float,
        opening_date: str,
        bank: str | None = None,
        agency: str | None = None,
        account_number: str | None = None,
    ) -> Account:
        account = Account(
            name=name,
            bank=bank,
            agency=agency,
            account_number=account_number,
            type=type,
            entity=entity,
            opening_balance=opening_balance,
            opening_date=opening_date,
        )
        self.store.create_account(account)
        # Create opening balance snapshot
        self.store.create_snapshot(
            BalanceSnapshot(
                account_id=account.id,
                date=opening_date,
                balance=opening_balance,
                source="opening",
            )
        )
        return account

    def get_accounts(self, entity: str | None = None) -> list[Account]:
        if entity:
            return self.store.get_accounts_by_entity(entity)
        return self.store.get_all_accounts()

    def find_account(self, account_number: str) -> Account | None:
        return self.store.get_account_by_number(account_number)

    # --- Import ---

    def import_ofx(self, content: str, account_id: str | None = None) -> dict:
        """Import transactions from OFX content.

        If account_id is not provided, tries to match by account number in OFX.
        Returns dict with account_id, imported count, skipped count, ledger_balance.
        """
        stmt = parse_ofx(content)

        # Find or require account
        if not account_id:
            account = self.store.get_account_by_number(stmt.account_id)
            if not account:
                raise ValueError(
                    f"No account found for OFX account {stmt.account_id}. "
                    f"Create the account first or pass account_id explicitly."
                )
            account_id = account.id

        # Build transactions (filter out informational entries from Itaú)
        SKIP_PATTERNS = ["SALDO ANTERIOR", "SALDO TOTAL DISPON"]
        txns = []
        for otxn in stmt.transactions:
            memo_upper = otxn.memo.strip().upper()
            if any(pat.upper() in memo_upper for pat in SKIP_PATTERNS):
                continue
            txn = Transaction(
                account_id=account_id,
                date=otxn.date,
                description=otxn.memo,
                memo=otxn.memo,
                amount=otxn.amount,
                type="credit" if otxn.amount >= 0 else "debit",
                fit_id=otxn.fit_id,
            )
            txns.append(txn)

        total = len(txns)
        inserted = self.store.bulk_create_transactions(txns)

        # Record ledger balance as snapshot
        if stmt.ledger_balance is not None and stmt.ledger_date:
            self.store.create_snapshot(
                BalanceSnapshot(
                    account_id=account_id,
                    date=stmt.ledger_date,
                    balance=stmt.ledger_balance,
                    source="ofx",
                )
            )

        return {
            "account_id": account_id,
            "imported": inserted,
            "skipped": total - inserted,
            "ledger_balance": stmt.ledger_balance,
            "period": f"{stmt.start_date} to {stmt.end_date}",
        }

    def import_itau_csv(self, path: str, account_id: str | None = None) -> dict:
        """Import from Itaú credit card CSV file.

        If account_id is not provided, tries to match by card number suffix.
        """
        raw = Path(path).read_bytes()
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            content = raw.decode("latin-1")
        stmt = parse_itau_cc_csv(content)

        if not account_id:
            # Try matching by card suffix in account_number
            suffix = stmt.card_number.split(".")[-1] if stmt.card_number else ""
            if suffix:
                for acc in self.store.get_all_accounts():
                    if acc.account_number and suffix in acc.account_number:
                        account_id = acc.id
                        break
            if not account_id:
                raise ValueError(
                    f"No account found for Itaú card {stmt.card_number}. "
                    f"Create the account first or pass account_id explicitly."
                )

        txns = []
        for itxn in stmt.transactions:
            txns.append(
                Transaction(
                    account_id=account_id,
                    date=itxn.date,
                    description=itxn.description,
                    memo=itxn.description,
                    amount=itxn.amount,
                    type="debit",
                    fit_id=itxn.fit_id,
                )
            )

        inserted = self.store.bulk_create_transactions(txns)

        return {
            "account_id": account_id,
            "card": stmt.card_number,
            "closing_date": stmt.closing_date,
            "imported": inserted,
            "skipped": len(txns) - inserted,
            "total_fatura": stmt.total,
        }

    def import_ofx_file(self, path: str, account_id: str | None = None) -> dict:
        """Import from an OFX file path. Detects encoding from OFX header."""
        raw = Path(path).read_bytes()
        # Detect encoding from OFX header
        header = raw[:500].decode("ascii", errors="ignore").upper()
        if "UTF-8" in header or "UTF8" in header:
            content = raw.decode("utf-8")
        else:
            content = raw.decode("latin-1")
        return self.import_ofx(content, account_id)

    # --- Transactions ---

    def get_transactions(
        self,
        account_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[Transaction]:
        return self.store.get_transactions(account_id, start_date, end_date)

    # --- Snapshots ---

    def record_balance(
        self, account_id: str, date: str, balance: float, source: str = "manual"
    ) -> BalanceSnapshot:
        snap = BalanceSnapshot(
            account_id=account_id,
            date=date,
            balance=balance,
            source=source,
        )
        return self.store.create_snapshot(snap)

    def get_current_balance(self, account_id: str) -> float | None:
        snap = self.store.get_latest_snapshot(account_id)
        return snap.balance if snap else None

    # --- Reports ---

    def runway(self, months_lookback: int = 3) -> dict:
        """Calculate runway based on recent burn rate.

        Returns dict with total_balance, monthly_burn, runway_months, by_entity.
        """
        accounts = self.store.get_all_accounts()
        snapshots = {}
        for acc in accounts:
            snap = self.store.get_latest_snapshot(acc.id)
            if snap:
                snapshots[acc.id] = snap

        balances = consolidated_balance(accounts, snapshots)

        # Get all transactions for burn calculation
        all_txns = self.store.get_transactions()
        monthly = summarize_by_month(all_txns)
        burn = calculate_monthly_burn(all_txns)
        runway_months = calculate_runway(balances["total"], burn)

        return {
            "balances": balances,
            "monthly_summary": monthly,
            "monthly_burn": burn,
            "runway_months": runway_months,
        }

    def monthly_report(self, account_id: str | None = None) -> dict[str, dict]:
        """Get income/expense/net by month."""
        txns = self.store.get_transactions(account_id=account_id)
        return summarize_by_month(txns)

    # --- Context for the Espelho ---

    def financial_context(self) -> str:
        """Generate a text summary for the tesoureira persona to use."""
        accounts = self.store.get_all_accounts()
        if not accounts:
            return "Nenhuma conta cadastrada no sistema financeiro."

        lines = ["=== Situação Financeira ===\n"]

        total = 0.0
        for acc in accounts:
            snap = self.store.get_latest_snapshot(acc.id)
            balance = snap.balance if snap else acc.opening_balance
            snap_date = snap.date if snap else acc.opening_date
            entity_label = "PF" if acc.entity == "personal" else "PJ"
            type_label = "CC" if acc.type == "checking" else "Cartão"
            lines.append(
                f"[{entity_label}] {acc.bank} {type_label} — R$ {balance:,.2f} (em {snap_date})"
            )
            total += balance

        lines.append(f"\nTotal consolidado: R$ {total:,.2f}")

        # Monthly summary
        all_txns = self.store.get_transactions()
        if all_txns:
            monthly = summarize_by_month(all_txns)
            lines.append("\n--- Fluxo mensal ---")
            for month, data in monthly.items():
                lines.append(
                    f"{month}: entrada R$ {data['income']:,.2f} | "
                    f"saída R$ {abs(data['expense']):,.2f} | "
                    f"líquido R$ {data['net']:,.2f}"
                )

            burn = calculate_monthly_burn(all_txns)
            runway = calculate_runway(total, burn)
            if runway is not None:
                lines.append(f"\nBurn mensal médio: R$ {abs(burn):,.2f}")
                lines.append(f"Runway estimado: {runway:.1f} meses")

        return "\n".join(lines)
