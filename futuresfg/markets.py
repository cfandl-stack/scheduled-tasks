"""Market sources: BTC price (RSI/volatility), VIX and the dollar index."""
import csv
import io
import logging
import math
from datetime import date

import numpy as np
import pandas as pd

from feargreed import data as yfdata
from futuresfg import config, http
from futuresfg.http import require

logger = logging.getLogger(__name__)


def _yf_close(ticker: str) -> pd.Series:
    raw = yfdata.download([ticker], period=config.YF_PERIOD)
    close = yfdata.extract_field(raw, "Close", [ticker])
    if ticker not in close.columns:
        raise ValueError(f"No close prices for {ticker}")
    return close[ticker].dropna()


def _to_dict(series: pd.Series, start: date) -> dict[str, float]:
    series = series.dropna()
    return {d.date().isoformat(): float(v) for d, v in series.loc[pd.Timestamp(start):].items()}


def rsi(close: pd.Series, period: int = config.RSI_PERIOD) -> pd.Series:
    """Wilder's RSI."""
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = gain / loss
    out = 100.0 - 100.0 / (1.0 + rs)
    return out.where(loss > 0, 100.0).where(gain.notna())


def realized_vol(close: pd.Series, window: int = config.VOL_WINDOW) -> pd.Series:
    """Annualised (365 days) realised volatility of daily log returns, in %."""
    rets = np.log(close / close.shift(1))
    return rets.rolling(window, min_periods=window).std() * math.sqrt(365) * 100.0


def rsi_vol_from_close(close: pd.Series, start: date) -> dict[str, dict[str, float]]:
    frame = pd.DataFrame({"rsi": rsi(close), "vol": realized_vol(close)}).dropna()
    frame = frame.loc[pd.Timestamp(start):]
    return {d.date().isoformat(): {"rsi": float(r.rsi), "vol": float(r.vol)} for d, r in frame.iterrows()}


def fetch_yf_rsi_vol(start: date) -> dict[str, dict[str, float]]:
    return require(rsi_vol_from_close(_yf_close(config.BTC_TICKER), start), "BTC RSI/vol")


def fetch_yf_vix(start: date) -> dict[str, float]:
    return require(_to_dict(_yf_close(config.VIX_TICKER), start), "VIX")


def dollar_from_levels(levels: pd.Series, start: date) -> dict[str, dict[str, float]]:
    levels = levels.dropna().sort_index()
    change = levels.pct_change(config.DXY_CHANGE_DAYS, fill_method=None) * 100.0
    frame = pd.DataFrame({"level": levels, "change": change}).dropna().loc[pd.Timestamp(start):]
    return {d.date().isoformat(): {"level": float(r.level), "change": float(r.change)} for d, r in frame.iterrows()}


def parse_fred_csv(text: str) -> pd.Series:
    rows = list(csv.reader(io.StringIO(text.strip())))
    if len(rows) < 2 or len(rows[0]) < 2:
        raise ValueError(f"Unexpected FRED CSV: {text[:200]}")
    values = {}
    for row in rows[1:]:
        if len(row) < 2:
            continue
        try:
            values[pd.Timestamp(row[0])] = float(row[1])
        except ValueError:
            continue  # "." marks a missing observation
    return pd.Series(values, dtype=float).sort_index()


def fetch_fred_dollar(start: date) -> dict[str, dict[str, float]]:
    text = http.get_text(config.FRED_CSV, {"id": config.FRED_DOLLAR_SERIES}, headers={"Accept": "text/csv"})
    return require(dollar_from_levels(parse_fred_csv(text), start), "FRED dollar")


def fetch_yf_dollar(start: date) -> dict[str, dict[str, float]]:
    return require(dollar_from_levels(_yf_close(config.DXY_TICKER), start), "DXY")
