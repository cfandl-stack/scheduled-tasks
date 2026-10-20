import numpy as np
import pandas as pd
import pytest

from feargreed import indicators
from feargreed.data import extract_field
from tests.feargreed.conftest import make_download


def _frame(cols: dict) -> pd.DataFrame:
    n = len(next(iter(cols.values())))
    return pd.DataFrame(cols, index=pd.bdate_range("2024-01-01", periods=n), dtype=float)


class TestIndicators:
    def test_momentum_above_sma_positive(self):
        close = _frame({"^GSPC": [100.0] * 9 + [110.0]})
        m = indicators.momentum(close, "^GSPC", window=10)
        assert m.iloc[-1] == pytest.approx((110 / 101 - 1) * 100)

    def test_missing_ticker_raises(self):
        with pytest.raises(KeyError):
            indicators.momentum(_frame({"X": [1.0, 2.0]}), "^GSPC")

    def test_net_new_highs(self):
        close = _frame({
            "UP": [1, 2, 3, 4, 5],
            "DOWN": [5, 4, 3, 2, 1],
            "UP2": [1, 2, 3, 4, 6],
            "MID": [1, 1, 1, 3, 2],
        })
        s = indicators.net_new_highs(close, window=3)
        assert s.iloc[-1] == pytest.approx((2 - 1) / 4 * 100)

    def test_net_up_volume(self):
        close = _frame({"A": [1, 2, 3, 4], "B": [4, 3, 2, 1]})
        volume = _frame({"A": [10, 30, 30, 30], "B": [10, 10, 10, 10]})
        s = indicators.net_up_volume(close, volume, window=3)
        assert s.iloc[-1] == pytest.approx((90 - 30) / 120 * 100)

    def test_vix_term_structure(self):
        close = _frame({"^VIX": [20.0] * 5, "^VIX3M": [25.0] * 5})
        s = indicators.vix_term_structure(close, "^VIX", "^VIX3M", smoothing=5)
        assert s.iloc[-1] == pytest.approx(0.8)

    def test_relative_return(self):
        close = _frame({"SPY": [100, 105, 110], "IEF": [100, 100, 101]})
        s = indicators.relative_return(close, "SPY", "IEF", window=2)
        assert s.iloc[-1] == pytest.approx(10.0 - 1.0)


class TestExtractField:
    def test_ticker_first_multiindex(self):
        raw = make_download(n_days=30)(["SPY", "IEF"])
        close = extract_field(raw, "Close", ["SPY", "IEF"])
        assert list(close.columns) == ["SPY", "IEF"]
        assert len(close) == 30

    def test_field_first_multiindex(self):
        raw = make_download(n_days=30)(["SPY", "IEF"]).swaplevel(axis=1).sort_index(axis=1)
        close = extract_field(raw, "Close", ["SPY", "IEF"])
        assert set(close.columns) == {"SPY", "IEF"}

    def test_flat_columns_single_ticker(self):
        raw = make_download(n_days=30)(["SPY"])["SPY"]
        close = extract_field(raw, "Close", ["SPY"])
        assert list(close.columns) == ["SPY"]

    def test_all_nan_ticker_dropped(self):
        raw = make_download(n_days=30, missing=("IEF",))(["SPY", "IEF"])
        assert list(extract_field(raw, "Close", ["SPY", "IEF"]).columns) == ["SPY"]

    def test_tz_aware_index_normalized(self):
        raw = make_download(n_days=5)(["SPY"])
        raw.index = raw.index.tz_localize("America/New_York")
        close = extract_field(raw, "Close", ["SPY"])
        assert close.index.tz is None

    def test_missing_field_raises(self):
        raw = make_download(n_days=5)(["SPY"])
        with pytest.raises(KeyError):
            extract_field(raw, "Adj Close", ["SPY"])

    def test_numeric_values(self):
        raw = make_download(n_days=5)(["SPY"])
        assert np.issubdtype(extract_field(raw, "Close", ["SPY"])["SPY"].dtype, np.floating)
