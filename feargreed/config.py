from dataclasses import dataclass

SP500 = "^GSPC"
VIX = "^VIX"
VIX3M = "^VIX3M"
STOCKS = "SPY"
TREASURIES = "IEF"
JUNK = "HYG"

MARKET_TICKERS: list[str] = [SP500, VIX, VIX3M, STOCKS, TREASURIES, JUNK]

# Proxy for NYSE new highs/lows and up/down volume: ~100 large US stocks
# (roughly the S&P 100). Tickers that fail to download are skipped.
BREADTH_BASKET: list[str] = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "BRK-B", "AVGO", "TSLA", "LLY",
    "JPM", "V", "UNH", "XOM", "MA", "JNJ", "PG", "HD", "COST", "ABBV",
    "MRK", "WMT", "NFLX", "CRM", "BAC", "CVX", "KO", "AMD", "PEP", "ORCL",
    "TMO", "ADBE", "LIN", "ACN", "MCD", "CSCO", "ABT", "WFC", "DHR", "IBM",
    "GE", "QCOM", "TXN", "INTU", "AMGN", "PM", "VZ", "CAT", "ISRG", "NOW",
    "DIS", "CMCSA", "PFE", "UNP", "GS", "SPGI", "AMAT", "RTX", "NEE", "LOW",
    "T", "HON", "BKNG", "UBER", "COP", "BLK", "AXP", "MS", "ELV", "PLD",
    "SYK", "LMT", "MDT", "TJX", "C", "SCHW", "BMY", "GILD", "DE", "MDLZ",
    "ADP", "CB", "MO", "SO", "CI", "DUK", "BA", "UPS", "CVS", "SBUX",
    "INTC", "PYPL", "TGT", "GD", "USB", "F", "GM", "MET", "EMR", "FDX",
    "COF", "AIG", "BK", "CL", "MU", "ADI",
]

# 3y so that every day of the 1-year history has a full lookback
# (252d for 52w highs + 252d percentile window).
HISTORY_PERIOD = "3y"

MOMENTUM_SMA = 125
VOLATILITY_SMA = 50
HIGH_LOW_WINDOW = 252
BREADTH_WINDOW = 20
PUT_CALL_SMOOTHING = 5
RETURN_WINDOW = 20

PERCENTILE_WINDOW = 252
PERCENTILE_MIN_PERIODS = 126
HISTORY_DAYS = 252
MIN_COMPONENTS = 4
MAX_FFILL_DAYS = 3

OUTPUT_PATH = "dashboard/data/feargreed.json"


@dataclass(frozen=True)
class RatingBand:
    upper: int
    rating: str
    rating_de: str


RATING_BANDS: list[RatingBand] = [
    RatingBand(24, "Extreme Fear", "Extreme Angst"),
    RatingBand(44, "Fear", "Angst"),
    RatingBand(55, "Neutral", "Neutral"),
    RatingBand(75, "Greed", "Gier"),
    RatingBand(100, "Extreme Greed", "Extreme Gier"),
]
