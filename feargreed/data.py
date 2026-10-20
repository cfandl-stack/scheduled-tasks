import logging

import pandas as pd
import yfinance as yf

from feargreed.config import HISTORY_PERIOD

logger = logging.getLogger(__name__)


def download(tickers: list[str], period: str = HISTORY_PERIOD) -> pd.DataFrame:
    logger.info("Downloading %d tickers (period=%s)", len(tickers), period)
    df = yf.download(
        tickers,
        period=period,
        auto_adjust=True,
        group_by="ticker",
        progress=False,
        threads=True,
    )
    if df is None or df.empty:
        raise ValueError(f"No data returned for {len(tickers)} tickers")
    return df


def extract_field(df: pd.DataFrame, field: str, tickers: list[str]) -> pd.DataFrame:
    """Return a date x ticker frame for one OHLCV field, whatever the column layout."""
    if isinstance(df.columns, pd.MultiIndex):
        level = next(
            (i for i in range(df.columns.nlevels) if field in df.columns.get_level_values(i)),
            None,
        )
        if level is None:
            raise KeyError(f"Field {field!r} not in downloaded data")
        out = df.xs(field, axis=1, level=level)
        if isinstance(out, pd.Series):
            out = out.to_frame(tickers[0] if len(tickers) == 1 else field)
    else:
        if field not in df.columns:
            raise KeyError(f"Field {field!r} not in downloaded data")
        if len(tickers) != 1:
            raise ValueError("Flat columns but multiple tickers requested")
        out = df[[field]].rename(columns={field: tickers[0]})

    out = out.apply(pd.to_numeric, errors="coerce")
    out.index = _naive_index(out.index)
    out = out.sort_index()
    out = out[~out.index.duplicated(keep="last")]
    return out.dropna(axis=1, how="all")


def _naive_index(index: pd.Index) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(pd.to_datetime(index))
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    return idx.normalize()
