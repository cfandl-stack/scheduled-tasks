"""German number formatting for value labels (decimal comma, typographic minus)."""

MINUS = "−"


def number(value: float, decimals: int = 1, signed: bool = False) -> str:
    text = f"{abs(value):,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    is_zero = text.strip("0,.") == ""
    if value < 0 and not is_zero:
        return MINUS + text
    if signed and not is_zero:
        return "+" + text
    return text


def percent(value: float, decimals: int = 1, signed: bool = True) -> str:
    return f"{number(value, decimals, signed)} %"


def millions(value: float, signed: bool = False) -> str:
    m = value / 1e6
    return number(m, 0 if abs(m) >= 10 else 1, signed)


def usd_millions(value: float, signed: bool = False) -> str:
    return f"{millions(value, signed)} Mio. $"


def long_short_millions(long_usd: float, short_usd: float) -> str:
    decimals = 0 if max(long_usd, short_usd) >= 10e6 else 1
    return f"{number(long_usd / 1e6, decimals)} / {number(short_usd / 1e6, decimals)} Mio. $"
