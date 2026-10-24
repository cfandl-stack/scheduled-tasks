"""Futures-market sources: funding, open interest, long/short ratio, liquidations.

Every fetch_* function takes the first date wanted and returns {"YYYY-MM-DD": raw value}
for UTC days; it raises on any failure so the caller can fall back to the next source.
"""
import logging
import statistics
import time
from collections import defaultdict
from datetime import date
from typing import Any

import pandas as pd

from futuresfg import config, http
from futuresfg.http import date_to_ms, ms_to_date, require

logger = logging.getLogger(__name__)


def okx_data(payload: dict) -> list:
    if not isinstance(payload, dict) or str(payload.get("code")) != "0":
        raise ValueError(f"OKX error: {str(payload)[:200]}")
    return payload.get("data") or []


def _bybit_list(payload: dict) -> list:
    if not isinstance(payload, dict) or payload.get("retCode") != 0:
        raise ValueError(f"Bybit error: {str(payload)[:200]}")
    return (payload.get("result") or {}).get("list") or []



def _from(data: dict[str, Any], start: date) -> dict[str, Any]:
    first = start.isoformat()
    return {d: v for d, v in data.items() if d >= first}


# ─── Funding ──────────────────────────────────────────────

def daily_funding(points: list[tuple[int, float]]) -> dict[str, float]:
    """Daily mean funding rate in % per 8h, whatever the exchange's funding interval."""
    if not points:
        return {}
    points = sorted(points)
    gaps = [b[0] - a[0] for a, b in zip(points, points[1:]) if b[0] > a[0]]
    interval_h = statistics.median(gaps) / 3_600_000 if gaps else 8.0
    scale = 8.0 / interval_h
    buckets: dict[str, list[float]] = defaultdict(list)
    for ts, rate in points:
        buckets[ms_to_date(ts)].append(rate)
    return {d: sum(v) / len(v) * scale * 100.0 for d, v in sorted(buckets.items())}


def parse_okx_funding(payload: dict) -> list[tuple[int, float]]:
    out = []
    for row in okx_data(payload):
        rate = row.get("realizedRate") or row.get("fundingRate")
        if rate not in (None, ""):
            out.append((int(row["fundingTime"]), float(rate)))
    return out


def fetch_okx_funding(start: date) -> dict[str, float]:
    points: list[tuple[int, float]] = []
    after = None
    for _ in range(config.MAX_PAGES):
        params = {"instId": config.OKX_SWAP, "limit": 100}
        if after:
            params["after"] = after
        page = parse_okx_funding(http.get_json(f"{config.OKX}/api/v5/public/funding-rate-history", params))
        if not page:
            break
        points += page
        oldest = min(ts for ts, _ in page)
        if oldest < date_to_ms(start) or oldest == after:
            break
        after = oldest
        time.sleep(config.PAGE_PAUSE)
    return require(_from(daily_funding(points), start), "OKX funding")


def parse_hyperliquid_funding(payload: list) -> list[tuple[int, float]]:
    if not isinstance(payload, list):
        raise ValueError(f"Hyperliquid error: {str(payload)[:200]}")
    return [(int(r["time"]), float(r["fundingRate"])) for r in payload]


def fetch_hyperliquid_funding(start: date) -> dict[str, float]:
    points: list[tuple[int, float]] = []
    since = date_to_ms(start)
    for _ in range(config.MAX_PAGES):
        page = parse_hyperliquid_funding(
            http.post_json(config.HYPERLIQUID, {"type": "fundingHistory", "coin": "BTC", "startTime": since})
        )
        if not page:
            break
        points += page
        last = max(ts for ts, _ in page)
        if len(page) < 500 or last < since:
            break
        since = last + 1
        time.sleep(config.PAGE_PAUSE)
    return require(daily_funding(points), "Hyperliquid funding")


def parse_binance_funding(payload: list) -> list[tuple[int, float]]:
    if not isinstance(payload, list):
        raise ValueError(f"Binance error: {str(payload)[:200]}")
    return [(int(r["fundingTime"]), float(r["fundingRate"])) for r in payload]


def fetch_binance_funding(start: date) -> dict[str, float]:
    points: list[tuple[int, float]] = []
    since = date_to_ms(start)
    for _ in range(config.MAX_PAGES):
        page = parse_binance_funding(http.get_json(
            f"{config.BINANCE_FAPI}/fapi/v1/fundingRate",
            {"symbol": config.BINANCE_SYMBOL, "startTime": since, "limit": 1000},
        ))
        if not page:
            break
        points += page
        if len(page) < 1000:
            break
        since = max(ts for ts, _ in page) + 1
    return require(daily_funding(points), "Binance funding")


# ─── Open interest (24h change in %) ──────────────────────

def daily_pct_change(levels: dict[str, float], periods: int = 1) -> dict[str, float]:
    """% change vs. the level `periods` calendar days earlier (gaps give no value)."""
    if not levels:
        return {}
    s = pd.Series(levels, dtype=float)
    s.index = pd.to_datetime(s.index)
    s = s[~s.index.duplicated(keep="last")].sort_index()
    s = s.asfreq("D")
    change = (s / s.shift(periods) - 1.0) * 100.0
    return {d.date().isoformat(): float(v) for d, v in change.dropna().items()}


def _okx_rubik(path: str) -> list:
    # Returns everything OKX keeps for 1D (roughly half a year), newest first.
    return okx_data(http.get_json(f"{config.OKX}/api/v5/rubik/stat/contracts/{path}", {"ccy": "BTC", "period": "1D"}))


def parse_okx_open_interest(payload: dict) -> dict[str, float]:
    return {ms_to_date(r[0]): float(r[1]) for r in okx_data(payload)}


def fetch_okx_oi_change(start: date) -> dict[str, float]:
    levels = parse_okx_open_interest({"code": "0", "data": _okx_rubik("open-interest-volume")})
    return require(daily_pct_change(levels), "OKX open interest")


def parse_bybit_open_interest(payload: dict) -> tuple[dict[str, float], str]:
    rows = _bybit_list(payload)
    levels = {ms_to_date(r["timestamp"]): float(r["openInterest"]) for r in rows}
    return levels, (payload.get("result") or {}).get("nextPageCursor") or ""


def fetch_bybit_oi_change(start: date) -> dict[str, float]:
    levels: dict[str, float] = {}
    cursor = ""
    for _ in range(config.MAX_PAGES):
        params = {"category": "linear", "symbol": config.BINANCE_SYMBOL, "intervalTime": "1d", "limit": 200}
        if cursor:
            params["cursor"] = cursor
        page, cursor = parse_bybit_open_interest(http.get_json(f"{config.BYBIT}/v5/market/open-interest", params))
        levels.update(page)
        if not page or not cursor or min(page) < start.isoformat():
            break
    return require(daily_pct_change(levels), "Bybit open interest")


def parse_binance_open_interest(payload: list) -> dict[str, float]:
    if not isinstance(payload, list):
        raise ValueError(f"Binance error: {str(payload)[:200]}")
    return {ms_to_date(r["timestamp"]): float(r["sumOpenInterestValue"]) for r in payload}


def fetch_binance_oi_change(start: date) -> dict[str, float]:
    levels = parse_binance_open_interest(http.get_json(
        f"{config.BINANCE_FAPI}/futures/data/openInterestHist",
        {"symbol": config.BINANCE_SYMBOL, "period": "1d", "limit": 30},
    ))
    return require(daily_pct_change(levels), "Binance open interest")


# ─── Long/short account ratio ─────────────────────────────

def parse_okx_long_short(payload: dict) -> dict[str, float]:
    return {ms_to_date(r[0]): float(r[1]) for r in okx_data(payload)}


def fetch_okx_long_short(start: date) -> dict[str, float]:
    data = parse_okx_long_short({"code": "0", "data": _okx_rubik("long-short-account-ratio")})
    return require(data, "OKX long/short")


def parse_bybit_long_short(payload: dict) -> dict[str, float]:
    out = {}
    for r in _bybit_list(payload):
        buy, sell = float(r["buyRatio"]), float(r["sellRatio"])
        if sell > 0:
            out[ms_to_date(r["timestamp"])] = buy / sell
    return out


def fetch_bybit_long_short(start: date) -> dict[str, float]:
    data = parse_bybit_long_short(http.get_json(
        f"{config.BYBIT}/v5/market/account-ratio",
        {"category": "linear", "symbol": config.BINANCE_SYMBOL, "period": "1d", "limit": 500},
    ))
    return require(data, "Bybit long/short")


def parse_binance_long_short(payload: list) -> dict[str, float]:
    if not isinstance(payload, list):
        raise ValueError(f"Binance error: {str(payload)[:200]}")
    return {ms_to_date(r["timestamp"]): float(r["longShortRatio"]) for r in payload}


def fetch_binance_long_short(start: date) -> dict[str, float]:
    data = parse_binance_long_short(http.get_json(
        f"{config.BINANCE_FAPI}/futures/data/globalLongShortAccountRatio",
        {"symbol": config.BINANCE_SYMBOL, "period": "1d", "limit": 30},
    ))
    return require(data, "Binance long/short")


# ─── Liquidations ({"long": $, "short": $} per day) ───────

def parse_coinglass_liquidations(payload: dict) -> dict[str, dict[str, float]]:
    if not isinstance(payload, dict) or str(payload.get("code")) != "0":
        raise ValueError(f"CoinGlass error: {str(payload)[:200]}")
    out = {}
    for r in payload.get("data") or []:
        long_ = r.get("aggregated_long_liquidation_usd", r.get("long_liquidation_usd"))
        short = r.get("aggregated_short_liquidation_usd", r.get("short_liquidation_usd"))
        if long_ is not None and short is not None:
            out[ms_to_date(r["time"])] = {"long": float(long_), "short": float(short)}
    return out


def fetch_coinglass_liquidations(start: date) -> dict[str, dict[str, float]]:
    key = config.coinglass_key()
    if not key:
        raise RuntimeError("COINGLASS_API_KEY not set")
    data = parse_coinglass_liquidations(http.get_json(
        f"{config.COINGLASS}/api/futures/liquidation/aggregated-history",
        {"exchange_list": config.COINGLASS_EXCHANGES, "symbol": "BTC", "interval": "1d",
         "start_time": date_to_ms(start), "limit": 1000},
        headers={"CG-API-KEY": key, "accept": "application/json"},
    ))
    return require(data, "CoinGlass liquidations")


def parse_okx_liquidations(payload: dict) -> list[tuple[int, str, float]]:
    """(ts, "long"|"short" = side that got liquidated, USD notional) per filled order."""
    out = []
    for group in okx_data(payload):
        for d in group.get("details") or []:
            pos = d.get("posSide")
            if pos not in ("long", "short"):
                pos = "long" if d.get("side") == "sell" else "short"
            usd = float(d["sz"]) * config.OKX_BTC_CT_VAL * float(d["bkPx"])
            out.append((int(d["ts"]), pos, usd))
    return out


def bucket_liquidations(orders: list[tuple[int, str, float]], complete_from_ms: int) -> dict[str, dict[str, float]]:
    """Daily long/short sums, only for days that start at or after `complete_from_ms`."""
    days: dict[str, dict[str, float]] = {}
    for ts, side, usd in orders:
        d = ms_to_date(ts)
        if date_to_ms(date.fromisoformat(d)) < complete_from_ms:
            continue
        bucket = days.setdefault(d, {"long": 0.0, "short": 0.0})
        bucket[side] += usd
    return dict(sorted(days.items()))


def fetch_okx_liquidations(start: date) -> dict[str, dict[str, float]]:
    orders: list[tuple[int, str, float]] = []
    after = None
    for _ in range(config.MAX_PAGES * 2):
        params = {"instType": "SWAP", "uly": config.OKX_SPOT, "state": "filled", "limit": 100}
        if after:
            params["after"] = after
        page = parse_okx_liquidations(http.get_json(f"{config.OKX}/api/v5/public/liquidation-orders", params))
        if not page:
            break
        orders += page
        oldest = min(ts for ts, _, _ in page)
        if oldest < date_to_ms(start) or oldest == after:
            break
        after = oldest
        time.sleep(config.PAGE_PAUSE)
    if not orders:
        raise ValueError("No OKX liquidation orders")
    # Days starting well before the oldest fetched order are incomplete (paging limit or retention).
    complete_from = min(ts for ts, _, _ in orders) - config.OKX_LIQ_MAX_GAP_HOURS * 3_600_000
    return require(_from(bucket_liquidations(orders, complete_from), start), "OKX liquidations")
