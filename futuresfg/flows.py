"""Flow sources: spot-ETF flows, stablecoin supply, Coinbase premium."""
import logging
import time
from datetime import UTC, date, datetime, timedelta

from bs4 import BeautifulSoup

from futuresfg import config, http
from futuresfg.derivatives import daily_pct_change, okx_data
from futuresfg.http import date_to_ms, ms_to_date, require

logger = logging.getLogger(__name__)



# ─── Spot Bitcoin ETF net flows (USD per day) ─────────────

def parse_coinglass_etf(payload: dict) -> dict[str, float]:
    if not isinstance(payload, dict) or str(payload.get("code")) != "0":
        raise ValueError(f"CoinGlass error: {str(payload)[:200]}")
    return {
        ms_to_date(r["timestamp"]): float(r["flow_usd"])
        for r in payload.get("data") or []
        if r.get("flow_usd") is not None
    }


def fetch_coinglass_etf(start: date) -> dict[str, float]:
    key = config.coinglass_key()
    if not key:
        raise RuntimeError("COINGLASS_API_KEY not set")
    data = parse_coinglass_etf(http.get_json(
        f"{config.COINGLASS}/api/etf/bitcoin/flow-history",
        headers={"CG-API-KEY": key, "accept": "application/json"},
    ))
    return require({d: v for d, v in data.items() if d >= start.isoformat()}, "CoinGlass ETF")


def parse_farside_number(text: str) -> float | None:
    t = text.strip().replace(",", "").replace("−", "-")
    if not t or t in ("-", "–", "—"):
        return None
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()")
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def _farside_date(text: str) -> str | None:
    try:
        return datetime.strptime(text.strip(), "%d %b %Y").date().isoformat()
    except ValueError:
        return None


def parse_farside(html: str) -> dict[str, float]:
    """Daily 'Total' column (last column, $m) of the Farside BTC ETF flow table, in USD."""
    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, float] = {}
    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        d = _farside_date(cells[0].get_text())
        if d is None:
            continue
        v = parse_farside_number(cells[-1].get_text())
        if v is not None:
            out[d] = v * 1e6
    return out


def fetch_farside_etf(start: date) -> dict[str, float]:
    data: dict[str, float] = {}
    for url in config.FARSIDE_URLS:
        try:
            data = parse_farside(http.get_text(url, headers={
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-GB,en;q=0.9",
            }))
        except Exception as exc:
            logger.info("Farside %s failed: %s", url, exc)
        if data:
            break
    return require({d: v for d, v in data.items() if d >= start.isoformat()}, "Farside ETF")


# ─── Stablecoin supply (7-day % change) ───────────────────

def parse_defillama_stablecoins(payload: list) -> dict[str, float]:
    if not isinstance(payload, list):
        raise ValueError(f"DefiLlama error: {str(payload)[:200]}")
    out = {}
    for r in payload:
        usd = (r.get("totalCirculatingUSD") or {}).get("peggedUSD")
        if usd:
            out[ms_to_date(int(r["date"]) * 1000)] = float(usd)
    return out


def fetch_defillama_stablecoins(start: date) -> dict[str, float]:
    levels = parse_defillama_stablecoins(http.get_json(config.DEFILLAMA_STABLES))
    change = daily_pct_change(levels, config.STABLECOIN_CHANGE_DAYS)
    return require({d: v for d, v in change.items() if d >= start.isoformat()}, "DefiLlama stablecoin")


# ─── Coinbase premium (% vs. offshore USDT price) ─────────

def parse_coinbase_candles(payload: list) -> dict[str, float]:
    if not isinstance(payload, list):
        raise ValueError(f"Coinbase error: {str(payload)[:200]}")
    # [time (s), low, high, open, close, volume]
    return {ms_to_date(int(r[0]) * 1000): float(r[4]) for r in payload}


def fetch_coinbase_closes(start: date) -> dict[str, float]:
    out: dict[str, float] = {}
    end = datetime.now(UTC).date() + timedelta(days=1)
    chunk_start = start
    while chunk_start < end:
        chunk_end = min(chunk_start + timedelta(days=299), end)
        out.update(parse_coinbase_candles(http.get_json(
            f"{config.COINBASE}/products/BTC-USD/candles",
            {"granularity": 86400, "start": f"{chunk_start.isoformat()}T00:00:00Z",
             "end": f"{chunk_end.isoformat()}T00:00:00Z"},
        )))
        chunk_start = chunk_end
        time.sleep(config.PAGE_PAUSE)
    return require(out, "Coinbase candles")


def parse_binance_klines(payload: list) -> dict[str, float]:
    if not isinstance(payload, list):
        raise ValueError(f"Binance error: {str(payload)[:200]}")
    # [open time (ms), open, high, low, close, volume, close time, ...]
    return {ms_to_date(r[0]): float(r[4]) for r in payload}


def fetch_binance_closes(start: date) -> dict[str, float]:
    out: dict[str, float] = {}
    since = date_to_ms(start)
    for _ in range(config.MAX_PAGES):
        payload = http.get_json(
            f"{config.BINANCE_DATA}/api/v3/klines",
            {"symbol": config.BINANCE_SYMBOL, "interval": "1d", "startTime": since, "limit": 1000},
        )
        page = parse_binance_klines(payload)
        out.update(page)
        if len(payload) < 1000:
            break
        since = int(payload[-1][0]) + 1
    return require(out, "Binance klines")


def parse_okx_candles(payload: dict) -> dict[str, float]:
    # [ts, open, high, low, close, vol, volCcy, volCcyQuote, confirm], newest first
    return {ms_to_date(r[0]): float(r[4]) for r in okx_data(payload)}


def fetch_okx_closes(start: date) -> dict[str, float]:
    out: dict[str, float] = {}
    after = None
    for _ in range(config.MAX_PAGES):
        params = {"instId": config.OKX_SPOT, "bar": "1Dutc", "limit": 100}
        if after:
            params["after"] = after
        payload = http.get_json(f"{config.OKX}/api/v5/market/history-candles", params)
        page = parse_okx_candles(payload)
        if not page:
            break
        out.update(page)
        oldest = min(int(r[0]) for r in payload["data"])
        if oldest <= date_to_ms(start) or oldest == after:
            break
        after = oldest
        time.sleep(config.PAGE_PAUSE)
    return require(out, "OKX candles")


def premium(coinbase: dict[str, float], other: dict[str, float]) -> dict[str, float]:
    return {
        d: (coinbase[d] - other[d]) / other[d] * 100.0
        for d in sorted(coinbase.keys() & other.keys())
        if other[d] > 0
    }


def fetch_premium_vs_binance(start: date) -> dict[str, float]:
    return require(premium(fetch_coinbase_closes(start), fetch_binance_closes(start)), "premium")


def fetch_premium_vs_okx(start: date) -> dict[str, float]:
    return require(premium(fetch_coinbase_closes(start), fetch_okx_closes(start)), "premium")
