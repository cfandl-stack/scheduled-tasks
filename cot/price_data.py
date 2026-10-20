import logging

import pandas as pd
import yfinance as yf

from cot.config import PRICE_HISTORY_PERIOD, SMA_LONG_PERIOD, SMA_SHORT_PERIOD, Commodity

logger = logging.getLogger(__name__)


def fetch_price_data(ticker: str, period: str = PRICE_HISTORY_PERIOD) -> pd.DataFrame:
    logger.info("Fetching price data for %s (period=%s)", ticker, period)
    df = yf.download(ticker, period=period, progress=False)

    if df.empty:
        raise ValueError(f"No price data returned for ticker {ticker}")

    return df


def calculate_smas(
    close_prices: pd.Series,
    short_period: int = SMA_SHORT_PERIOD,
    long_period: int = SMA_LONG_PERIOD,
) -> tuple[pd.Series, pd.Series]:
    sma_short = close_prices.rolling(window=short_period).mean()
    sma_long = close_prices.rolling(window=long_period).mean()
    return sma_short, sma_long


def check_trend_signal(commodity: Commodity) -> tuple[bool, dict]:
    try:
        df = fetch_price_data(commodity.futures_ticker)
    except ValueError:
        logger.warning("Could not fetch price data for %s", commodity.name)
        return False, {"error": f"No price data for {commodity.futures_ticker}"}

    close = df["Close"].squeeze()
    sma_short, sma_long = calculate_smas(close)

    latest_close = float(close.iloc[-1])
    latest_sma_short = float(sma_short.iloc[-1]) if pd.notna(sma_short.iloc[-1]) else None
    latest_sma_long = float(sma_long.iloc[-1]) if pd.notna(sma_long.iloc[-1]) else None

    if latest_sma_short is None or latest_sma_long is None:
        logger.warning(
            "%s: insufficient data for SMA calculation (sma50=%s, sma200=%s)",
            commodity.name,
            latest_sma_short,
            latest_sma_long,
        )
        signal = False
    else:
        signal = latest_close > latest_sma_short and latest_sma_short > latest_sma_long

    details = {
        "latest_close": round(latest_close, 2),
        "sma_50": round(latest_sma_short, 2) if latest_sma_short else None,
        "sma_200": round(latest_sma_long, 2) if latest_sma_long else None,
        "latest_date": str(close.index[-1].date()),
    }

    logger.info(
        "%s trend signal: %s (close=%.2f, sma50=%s, sma200=%s)",
        commodity.name,
        signal,
        latest_close,
        details["sma_50"],
        details["sma_200"],
    )
    return signal, details
