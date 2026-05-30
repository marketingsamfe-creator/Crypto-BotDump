import re
from typing import Optional, Tuple


CONTRACT_ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
SOLANA_ADDRESS_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def is_evm_address(address: str) -> bool:
    return bool(CONTRACT_ADDRESS_RE.match(address.strip()))


def is_solana_address(address: str) -> bool:
    return bool(SOLANA_ADDRESS_RE.match(address.strip()))


def is_valid_address(address: str) -> bool:
    return is_evm_address(address) or is_solana_address(address)


def parse_portfolio_line(line: str) -> Optional[Tuple[str, float, float]]:
    patterns = [
        r"^\s*(?P<sym>[A-Za-z0-9]+)\s*[:\-]?\s*(?P<qty>[\d,.]+)\s*(?:@|at)\s*\$?(?P<price>[\d,.]+)\s*$",
        r"^\s*(?P<sym>[A-Za-z0-9]+)\s*[,;\t]+\s*(?P<qty>[\d,.]+)\s*[,;\t]+\s*\$?(?P<price>[\d,.]+)\s*$",
        r"^\s*(?P<sym>[A-Za-z0-9]+)\s+(?P<qty>[\d,.]+)\s+(?P<price>[\d,.]+)\s*$",
    ]
    for pat in patterns:
        m = re.match(pat, line, re.IGNORECASE)
        if m:
            try:
                sym = m.group("sym").upper()
                qty = float(m.group("qty").replace(",", ""))
                price = float(m.group("price").replace(",", ""))
                if qty > 0 and price > 0:
                    return sym, qty, price
            except ValueError:
                pass
    return None


def validate_positive_decimal(value: str) -> Optional[float]:
    try:
        v = float(value.replace(",", ""))
        if v > 0:
            return v
        return None
    except (ValueError, AttributeError):
        return None
