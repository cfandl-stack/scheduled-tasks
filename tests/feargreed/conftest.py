import numpy as np
import pandas as pd
import pytest

N_DAYS = 760


def make_download(n_days: int = N_DAYS, seed: int = 0, missing: tuple[str, ...] = ()):
    """Fake yf.download returning yfinance-style (ticker, field) MultiIndex columns."""

    def fake_download(tickers, **kwargs):
        if isinstance(tickers, str):
            tickers = [tickers]
        rng = np.random.default_rng(seed)
        dates = pd.bdate_range(end="2026-10-19", periods=n_days)
        frames = {}
        for t in tickers:
            if t in missing:
                frames[t] = pd.DataFrame(np.nan, index=dates, columns=["Open", "High", "Low", "Close", "Volume"])
                continue
            base = 20.0 if t.startswith("^VIX") else 100.0
            vol = 0.03 if t.startswith("^VIX") else 0.01
            close = base * np.exp(np.cumsum(rng.normal(0.0003, vol, n_days)))
            frames[t] = pd.DataFrame(
                {
                    "Open": close,
                    "High": close * 1.01,
                    "Low": close * 0.99,
                    "Close": close,
                    "Volume": rng.integers(1_000, 10_000, n_days).astype(float),
                },
                index=dates,
            )
        return pd.concat(frames, axis=1)

    return fake_download


@pytest.fixture
def fake_download():
    return make_download()
