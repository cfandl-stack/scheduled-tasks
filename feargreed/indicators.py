"""Raw indicator series for each component. Higher value = more greed unless noted."""

import pandas as pd

from feargreed.config import (
    BREADTH_WINDOW,
    HIGH_LOW_WINDOW,
    MOMENTUM_SMA,
    PUT_CALL_SMOOTHING,
    RETURN_WINDOW,
    VOLATILITY_SMA,
)


def _series(close: pd.DataFrame, ticker: str) -> pd.Series:
    if ticker not in close.columns:
        raise KeyError(f"No data for {ticker}")
    s = close[ticker].dropna()
    if s.empty:
        raise KeyError(f"No data for {ticker}")
    return s


def pct_vs_sma(series: pd.Series, window: int) -> pd.Series:
    sma = series.rolling(window, min_periods=window).mean()
    return (series / sma - 1.0) * 100.0


def momentum(close: pd.DataFrame, ticker: str, window: int = MOMENTUM_SMA) -> pd.Series:
    return pct_vs_sma(_series(close, ticker), window).dropna()


def volatility(close: pd.DataFrame, ticker: str, window: int = VOLATILITY_SMA) -> pd.Series:
    """VIX vs. its moving average in % (higher = fear)."""
    return pct_vs_sma(_series(close, ticker), window).dropna()


def net_new_highs(close: pd.DataFrame, window: int = HIGH_LOW_WINDOW) -> pd.Series:
    """Share of basket at a 52w closing high minus share at a 52w closing low, in %."""
    if close.empty:
        raise ValueError("Empty basket")
    hi = close.rolling(window, min_periods=window).max()
    lo = close.rolling(window, min_periods=window).min()
    valid = hi.notna() & close.notna()
    n = valid.sum(axis=1)
    highs = ((close >= hi) & valid).sum(axis=1)
    lows = ((close <= lo) & valid).sum(axis=1)
    out = (highs - lows) / n.where(n > 0) * 100.0
    return out.dropna()


def net_up_volume(close: pd.DataFrame, volume: pd.DataFrame, window: int = BREADTH_WINDOW) -> pd.Series:
    """Rolling (up volume - down volume) / total volume of the basket, in %."""
    if close.empty or volume.empty:
        raise ValueError("Empty basket")
    common = close.columns.intersection(volume.columns)
    close, volume = close[common], volume[common].reindex(close.index)
    change = close.diff()
    up = volume.where(change > 0, 0.0).sum(axis=1)
    down = volume.where(change < 0, 0.0).sum(axis=1)
    total = volume.where(change.notna(), 0.0).sum(axis=1)
    net = (up - down).rolling(window, min_periods=window).sum()
    tot = total.rolling(window, min_periods=window).sum()
    return (net / tot.where(tot > 0) * 100.0).dropna()


def vix_term_structure(
    close: pd.DataFrame, front: str, back: str, smoothing: int = PUT_CALL_SMOOTHING
) -> pd.Series:
    """5-day average VIX/VIX3M ratio (higher = fear), proxy for the put/call ratio."""
    ratio = (_series(close, front) / _series(close, back)).dropna()
    return ratio.rolling(smoothing, min_periods=smoothing).mean().dropna()


def relative_return(close: pd.DataFrame, a: str, b: str, window: int = RETURN_WINDOW) -> pd.Series:
    """Return of a minus return of b over `window` days, in percentage points."""
    pair = pd.concat([_series(close, a), _series(close, b)], axis=1, keys=[a, b]).dropna()
    rets = pair.pct_change(window, fill_method=None) * 100.0
    return (rets[a] - rets[b]).dropna()
