"""OFX file parser for bank statements."""

import re
from dataclasses import dataclass, field


@dataclass
class OFXTransaction:
    type: str  # CREDIT, DEBIT
    date: str  # YYYY-MM-DD
    amount: float
    fit_id: str
    memo: str
    check_num: str | None = None


@dataclass
class OFXStatement:
    bank_id: str
    account_id: str
    account_type: str
    currency: str
    start_date: str
    end_date: str
    ledger_balance: float
    ledger_date: str
    transactions: list[OFXTransaction] = field(default_factory=list)


def _parse_date(raw: str) -> str:
    """Convert OFX date (YYYYMMDD...) to ISO date (YYYY-MM-DD)."""
    clean = raw.strip()[:8]
    return f"{clean[:4]}-{clean[4:6]}-{clean[6:8]}"


def _extract_tag(content: str, tag: str) -> str | None:
    """Extract value of an SGML tag (no closing tag, value until next < or newline)."""
    pattern = rf"<{tag}>([^<\n]+)"
    match = re.search(pattern, content, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def _extract_block(content: str, tag: str) -> str | None:
    """Extract content between <TAG> and </TAG>."""
    pattern = rf"<{tag}>(.*?)</{tag}>"
    match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def parse_ofx(content: str) -> OFXStatement:
    """Parse an OFX/SGML file and return structured statement data.

    Supports both bank statements (BANKMSGSRSV1) and credit cards (CREDITCARDMSGSRSV1).
    """
    # Detect credit card vs bank statement
    is_credit_card = "CREDITCARDMSGSRSV1" in content.upper()

    # Account info
    if is_credit_card:
        acct_block = _extract_block(content, "CCACCTFROM")
        bank_id = ""
        acct_id = _extract_tag(acct_block, "ACCTID") if acct_block else ""
        acct_type = "CREDIT_CARD"
    else:
        acct_block = _extract_block(content, "BANKACCTFROM")
        bank_id = _extract_tag(acct_block, "BANKID") if acct_block else ""
        acct_id = _extract_tag(acct_block, "ACCTID") if acct_block else ""
        acct_type = _extract_tag(acct_block, "ACCTTYPE") if acct_block else "CHECKING"

    # Currency
    currency = _extract_tag(content, "CURDEF") or "BRL"

    # Date range
    trans_list = _extract_block(content, "BANKTRANLIST")
    start_date = _parse_date(_extract_tag(trans_list, "DTSTART") or "") if trans_list else ""
    end_date = _parse_date(_extract_tag(trans_list, "DTEND") or "") if trans_list else ""

    # Ledger balance
    ledger_block = _extract_block(content, "LEDGERBAL")
    ledger_balance = float(_extract_tag(ledger_block, "BALAMT") or "0") if ledger_block else 0.0
    ledger_date = _parse_date(_extract_tag(ledger_block, "DTASOF") or "") if ledger_block else ""

    # Transactions
    transactions = []
    if trans_list:
        txn_blocks = re.findall(r"<STMTTRN>(.*?)</STMTTRN>", trans_list, re.DOTALL | re.IGNORECASE)
        for block in txn_blocks:
            trn_type = _extract_tag(block, "TRNTYPE") or "DEBIT"
            dt_posted = _extract_tag(block, "DTPOSTED") or ""
            amount = float(_extract_tag(block, "TRNAMT") or "0")
            fit_id = _extract_tag(block, "FITID") or ""
            memo = _extract_tag(block, "MEMO") or ""
            check_num = _extract_tag(block, "CHECKNUM")

            transactions.append(
                OFXTransaction(
                    type=trn_type.upper(),
                    date=_parse_date(dt_posted),
                    amount=amount,
                    fit_id=fit_id,
                    memo=memo,
                    check_num=check_num,
                )
            )

    return OFXStatement(
        bank_id=bank_id,
        account_id=acct_id,
        account_type=acct_type,
        currency=currency,
        start_date=start_date,
        end_date=end_date,
        ledger_balance=ledger_balance,
        ledger_date=ledger_date,
        transactions=transactions,
    )
