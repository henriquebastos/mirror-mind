"""Parser para CSV de fatura de cartão de crédito Itaú Empresas."""

import hashlib
import re
from dataclasses import dataclass, field


@dataclass
class ItauCCTransaction:
    date: str  # YYYY-MM-DD
    description: str
    amount: float
    fit_id: str
    type: str = "DEBIT"  # cartão de crédito = sempre débito


@dataclass
class ItauCCStatement:
    account_ref: str  # ex: "1584/99892-4"
    card_number: str  # ex: "5526.XXXX.XXXX.0571"
    closing_date: str  # vencimento da fatura
    total: float
    transactions: list[ItauCCTransaction] = field(default_factory=list)


def _parse_value(raw: str) -> float:
    """Converte 'RR$1.545,75' ou '-RR$3.339,16' para float."""
    clean = raw.replace("RR$", "").replace("R$", "").replace(".", "").replace(",", ".").strip()
    return float(clean)


def _resolve_date(day_month: str, closing_date: str) -> str:
    """Resolve '31/jan.' para YYYY-MM-DD baseado no vencimento da fatura.

    O mês do lançamento pode ser anterior ao mês de vencimento.
    Ex: fatura vence em 06/03/2026, lançamento em 31/jan → 2026-01-31.
    """
    MONTHS = {
        "jan": 1,
        "fev": 2,
        "mar": 3,
        "abr": 4,
        "mai": 5,
        "jun": 6,
        "jul": 7,
        "ago": 8,
        "set": 9,
        "out": 10,
        "nov": 11,
        "dez": 12,
    }

    match = re.match(r"(\d{1,2})/(\w+)\.", day_month.strip())
    if not match:
        return ""

    day = int(match.group(1))
    month_str = match.group(2).lower()
    month = MONTHS.get(month_str)
    if not month:
        return ""

    # Determinar ano a partir do vencimento da fatura
    closing_match = re.search(r"(\d{2})/(\d{2})/(\d{4})", closing_date)
    if closing_match:
        closing_year = int(closing_match.group(3))
        closing_month = int(closing_match.group(2))
    else:
        # Fallback: tentar YYYY
        year_match = re.search(r"(\d{4})", closing_date)
        closing_year = int(year_match.group(1)) if year_match else 2026
        closing_month = 12

    # Se o mês do lançamento é maior que o do vencimento, é do ano anterior
    year = closing_year if month <= closing_month else closing_year - 1

    return f"{year}-{month:02d}-{day:02d}"


def _generate_fit_id(date: str, description: str, amount: float) -> str:
    """Gera um ID único para a transação."""
    raw = f"{date}|{description}|{amount}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def parse_itau_cc_csv(content: str) -> ItauCCStatement:
    """Parse CSV de fatura de cartão Itaú Empresas (separador ';')."""
    lines = content.splitlines()

    # Extrair metadados
    account_ref = ""
    card_number = ""
    closing_date = ""
    total = 0.0

    for line in lines[:10]:
        if "Agência / Conta:" in line:
            m = re.search(r"Agência / Conta:\s*([\d/\-]+)", line)
            if m:
                account_ref = m.group(1)
        if "MASTERCARD" in line or "VISA" in line:
            m = re.search(r"(\d{4}\.\w+\.\w+\.\d{4})", line)
            if m:
                card_number = m.group(1)

    # Encontrar vencimento
    for line in lines:
        if "vencimento" in line.lower():
            next_idx = lines.index(line) + 1
            if next_idx < len(lines):
                m = re.search(r"(\d{2}/\d{2}/\w+)", lines[next_idx])
                if m:
                    raw_date = m.group(1)
                    # Resolver YYYY placeholder
                    closing_date = raw_date
                    break

    # Encontrar o ano real a partir de pagamentos ou contexto
    real_year = None
    for line in lines:
        m = re.search(r"PAGAMENTO EFETUADO (\d{4})-(\d{2})-(\d{2})", line)
        if m:
            real_year = int(m.group(1))
            break
    if not real_year:
        for line in lines:
            m = re.search(r"(\d{2}/\d{2}/(\d{4}))", line)
            if m:
                real_year = int(m.group(2))
                break

    # Reconstruir closing_date com ano real
    if "YYYY" in closing_date and real_year:
        closing_date = closing_date.replace("YYYY", str(real_year))

    # Extrair total da fatura
    for line in lines:
        if line.startswith("Total da fatura") and "RR$" in line:
            parts = [p for p in line.split(";") if "RR$" in p]
            if parts:
                total = _parse_value(parts[0])
                break

    # Parse transações
    transactions = []
    section = None  # 'nacional' ou 'internacional'

    def _norm(s: str) -> str:
        """Normaliza para comparação ignorando problemas de encoding."""
        return s.lower().replace("ã§", "ç").replace("ã£", "ã").replace("ã", "a").replace("ç", "c")

    for line in lines:
        stripped = line.strip().rstrip(";")
        normed = _norm(stripped)

        if "lancamentos nacionais" in normed and "total" not in normed:
            section = "nacional"
            continue
        elif "lancamentos internacionais" in normed and "total" not in normed:
            section = "internacional"
            continue
        elif "produtos" in normed and "encargos" in normed:
            section = None
            continue
        elif normed.startswith("total de ") or normed.startswith("repasse de iof"):
            continue
        elif normed.startswith("data;;descri"):
            continue

        if not section:
            continue

        parts = line.split(";")

        if section == "nacional":
            # data;;descrição;;;;;;;;valor;
            if len(parts) >= 11 and re.match(r"\d{1,2}/\w+\.", parts[0].strip()):
                date_raw = parts[0].strip()
                desc = parts[2].strip()
                value_raw = parts[10].strip() if parts[10].strip() else None
                if not value_raw or "RR$" not in value_raw:
                    continue
                amount = _parse_value(value_raw)
                date = _resolve_date(date_raw, closing_date)
                if date and desc:
                    fit_id = _generate_fit_id(date, desc, amount)
                    transactions.append(
                        ItauCCTransaction(
                            date=date,
                            description=desc,
                            amount=-amount,  # cartão = saída
                            fit_id=fit_id,
                        )
                    )

        elif section == "internacional":
            # data;;descrição;;moeda local;;moeda global;;cotação;;valor;
            if len(parts) >= 12 and re.match(r"\d{1,2}/\w+\.", parts[0].strip()):
                date_raw = parts[0].strip()
                desc = parts[2].strip()
                value_raw = parts[10].strip() if parts[10].strip() else None
                if not value_raw or "RR$" not in value_raw:
                    continue
                amount = _parse_value(value_raw)
                date = _resolve_date(date_raw, closing_date)
                if date and desc:
                    fit_id = _generate_fit_id(date, desc, amount)
                    transactions.append(
                        ItauCCTransaction(
                            date=date,
                            description=desc,
                            amount=-amount,
                            fit_id=fit_id,
                        )
                    )

    return ItauCCStatement(
        account_ref=account_ref,
        card_number=card_number,
        closing_date=closing_date,
        total=total,
        transactions=transactions,
    )
