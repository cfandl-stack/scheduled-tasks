import os

OUTPUT_PATH = "dashboard/data/futuresfg.json"
RAW_PATH = "dashboard/data/futuresfg_raw.json"

PERCENTILE_WINDOW = "365D"
PERCENTILE_MIN_PERIODS = 60
SMOOTHING_DAYS = 7
HISTORY_DAYS = 365
MIN_COMPONENTS = 5
DEFAULT_MAX_STALE_DAYS = 3
MAX_AS_OF_LAG_DAYS = 3

RAW_RETENTION_DAYS = 800
# Fetch this far back while a component's stored history is still short ...
BOOTSTRAP_DAYS = 420
BOOTSTRAP_MIN_ENTRIES = 300
# ... otherwise only re-fetch the last few days (fresh values overwrite stored ones).
REFRESH_OVERLAP_DAYS = 10

HTTP_TIMEOUT = 20
PAGE_PAUSE = 0.25
MAX_PAGES = 60
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)

OKX = "https://www.okx.com"
HYPERLIQUID = "https://api.hyperliquid.xyz/info"
BYBIT = "https://api.bybit.com"
BINANCE_FAPI = "https://fapi.binance.com"
BINANCE_DATA = "https://data-api.binance.vision"
COINBASE = "https://api.exchange.coinbase.com"
COINGLASS = "https://open-api-v4.coinglass.com"
DEFILLAMA_STABLES = "https://stablecoins.llama.fi/stablecoincharts/all"
FARSIDE_URLS = (
    "https://farside.co.uk/bitcoin-etf-flow-all-data/",
    "https://farside.co.uk/btc/",
)
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"

OKX_SWAP = "BTC-USDT-SWAP"
OKX_SPOT = "BTC-USDT"
OKX_BTC_CT_VAL = 0.01  # BTC per BTC-USDT-SWAP contract
# OKX keeps only ~24 h of liquidation orders, so the daily run (cron 00:20 UTC, but GitHub
# starts it around 05:00 UTC) never sees the whole previous day. Count a day as complete
# if at most this much of its start is missing.
OKX_LIQ_MAX_GAP_HOURS = 8
BINANCE_SYMBOL = "BTCUSDT"
COINGLASS_EXCHANGES = "Binance,OKX,Bybit,Bitget,Hyperliquid,Gate,HTX,Bitmex,Deribit"

BTC_TICKER = "BTC-USD"
VIX_TICKER = "^VIX"
DXY_TICKER = "DX-Y.NYB"
FRED_DOLLAR_SERIES = "DTWEXBGS"
YF_PERIOD = "3y"

RSI_PERIOD = 14
VOL_WINDOW = 30
STABLECOIN_CHANGE_DAYS = 7
DXY_CHANGE_DAYS = 20


def coinglass_key() -> str | None:
    return os.environ.get("COINGLASS_API_KEY") or None
