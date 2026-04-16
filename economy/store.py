"""CRUD operations for economy tables."""

import sqlite3

from economy.models import Account, BalanceSnapshot, Category, Transaction


class EconomyStore:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # --- Accounts ---

    def create_account(self, account: Account) -> Account:
        self.conn.execute(
            """INSERT INTO eco_accounts
               (id, name, bank, agency, account_number, type, entity,
                opening_balance, opening_date, created_at, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                account.id,
                account.name,
                account.bank,
                account.agency,
                account.account_number,
                account.type,
                account.entity,
                account.opening_balance,
                account.opening_date,
                account.created_at,
                account.metadata,
            ),
        )
        self.conn.commit()
        return account

    def get_account(self, account_id: str) -> Account | None:
        row = self.conn.execute("SELECT * FROM eco_accounts WHERE id = ?", (account_id,)).fetchone()
        if not row:
            return None
        return Account(**dict(row))

    def get_account_by_number(self, account_number: str) -> Account | None:
        row = self.conn.execute(
            "SELECT * FROM eco_accounts WHERE account_number = ?",
            (account_number,),
        ).fetchone()
        if not row:
            return None
        return Account(**dict(row))

    def get_all_accounts(self) -> list[Account]:
        rows = self.conn.execute(
            "SELECT * FROM eco_accounts ORDER BY entity, type, name"
        ).fetchall()
        return [Account(**dict(r)) for r in rows]

    def get_accounts_by_entity(self, entity: str) -> list[Account]:
        rows = self.conn.execute(
            "SELECT * FROM eco_accounts WHERE entity = ? ORDER BY type, name",
            (entity,),
        ).fetchall()
        return [Account(**dict(r)) for r in rows]

    def update_account(self, account_id: str, **kwargs) -> None:
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [account_id]
        self.conn.execute(f"UPDATE eco_accounts SET {sets} WHERE id = ?", vals)
        self.conn.commit()

    # --- Categories ---

    def create_category(self, category: Category) -> Category:
        self.conn.execute(
            """INSERT INTO eco_categories (id, name, type, created_at)
               VALUES (?, ?, ?, ?)""",
            (category.id, category.name, category.type, category.created_at),
        )
        self.conn.commit()
        return category

    def get_category_by_name(self, name: str) -> Category | None:
        row = self.conn.execute("SELECT * FROM eco_categories WHERE name = ?", (name,)).fetchone()
        if not row:
            return None
        return Category(**dict(row))

    def get_or_create_category(self, name: str, type: str) -> Category:
        existing = self.get_category_by_name(name)
        if existing:
            return existing
        cat = Category(name=name, type=type)
        return self.create_category(cat)

    def get_all_categories(self) -> list[Category]:
        rows = self.conn.execute("SELECT * FROM eco_categories ORDER BY type, name").fetchall()
        return [Category(**dict(r)) for r in rows]

    # --- Transactions ---

    def create_transaction(self, txn: Transaction) -> Transaction:
        self.conn.execute(
            """INSERT INTO eco_transactions
               (id, account_id, date, description, memo, amount, type,
                category_id, fit_id, balance_after, created_at, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                txn.id,
                txn.account_id,
                txn.date,
                txn.description,
                txn.memo,
                txn.amount,
                txn.type,
                txn.category_id,
                txn.fit_id,
                txn.balance_after,
                txn.created_at,
                txn.metadata,
            ),
        )
        self.conn.commit()
        return txn

    def get_transaction_by_fit_id(self, fit_id: str, account_id: str) -> Transaction | None:
        row = self.conn.execute(
            "SELECT * FROM eco_transactions WHERE fit_id = ? AND account_id = ?",
            (fit_id, account_id),
        ).fetchone()
        if not row:
            return None
        return Transaction(**dict(row))

    def get_transactions(
        self,
        account_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        category_id: str | None = None,
    ) -> list[Transaction]:
        query = "SELECT * FROM eco_transactions WHERE 1=1"
        params: list = []
        if account_id:
            query += " AND account_id = ?"
            params.append(account_id)
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        if category_id:
            query += " AND category_id = ?"
            params.append(category_id)
        query += " ORDER BY date, created_at"
        rows = self.conn.execute(query, params).fetchall()
        return [Transaction(**dict(r)) for r in rows]

    def bulk_create_transactions(self, txns: list[Transaction]) -> int:
        """Insert multiple transactions, skipping duplicates by fit_id. Returns count inserted."""
        inserted = 0
        for txn in txns:
            if txn.fit_id:
                existing = self.get_transaction_by_fit_id(txn.fit_id, txn.account_id)
                if existing:
                    continue
            self.conn.execute(
                """INSERT INTO eco_transactions
                   (id, account_id, date, description, memo, amount, type,
                    category_id, fit_id, balance_after, created_at, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    txn.id,
                    txn.account_id,
                    txn.date,
                    txn.description,
                    txn.memo,
                    txn.amount,
                    txn.type,
                    txn.category_id,
                    txn.fit_id,
                    txn.balance_after,
                    txn.created_at,
                    txn.metadata,
                ),
            )
            inserted += 1
        self.conn.commit()
        return inserted

    # --- Balance Snapshots ---

    def create_snapshot(self, snap: BalanceSnapshot) -> BalanceSnapshot:
        self.conn.execute(
            """INSERT INTO eco_balance_snapshots
               (id, account_id, date, balance, source, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (snap.id, snap.account_id, snap.date, snap.balance, snap.source, snap.created_at),
        )
        self.conn.commit()
        return snap

    def get_snapshots(
        self, account_id: str, start_date: str | None = None, end_date: str | None = None
    ) -> list[BalanceSnapshot]:
        query = "SELECT * FROM eco_balance_snapshots WHERE account_id = ?"
        params: list = [account_id]
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        query += " ORDER BY date"
        rows = self.conn.execute(query, params).fetchall()
        return [BalanceSnapshot(**dict(r)) for r in rows]

    def get_latest_snapshot(self, account_id: str) -> BalanceSnapshot | None:
        row = self.conn.execute(
            "SELECT * FROM eco_balance_snapshots WHERE account_id = ? ORDER BY date DESC LIMIT 1",
            (account_id,),
        ).fetchone()
        if not row:
            return None
        return BalanceSnapshot(**dict(row))
