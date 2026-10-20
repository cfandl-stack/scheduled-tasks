import numpy as np
import pandas as pd
import pytest
from unittest.mock import patch

from cot.config import Commodity
from cot.price_data import calculate_smas, check_trend_signal


@pytest.fixture
def sample_commodity():
    return Commodity("Gold", "088691", "GC=F", "UGL")


class TestCalculateSmas:
    def test_basic_sma_calculation(self):
        prices = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        sma_short, sma_long = calculate_smas(prices, short_period=3, long_period=5)

        assert np.isnan(sma_short.iloc[0])
        assert np.isnan(sma_short.iloc[1])
        assert sma_short.iloc[2] == pytest.approx(2.0)
        assert sma_short.iloc[3] == pytest.approx(3.0)
        assert sma_short.iloc[4] == pytest.approx(4.0)

        assert sma_long.iloc[4] == pytest.approx(3.0)

    def test_sma_with_constant_prices(self):
        prices = pd.Series([10.0] * 10)
        sma_short, sma_long = calculate_smas(prices, short_period=3, long_period=5)
        assert sma_short.iloc[-1] == pytest.approx(10.0)
        assert sma_long.iloc[-1] == pytest.approx(10.0)


class TestCheckTrendSignal:
    def _make_price_df(self, close_values):
        dates = pd.bdate_range("2023-01-01", periods=len(close_values))
        return pd.DataFrame(
            {"Close": close_values, "Open": close_values, "High": close_values, "Low": close_values, "Volume": 1000},
            index=dates,
        )

    @patch("cot.price_data.fetch_price_data")
    def test_uptrend_signal(self, mock_fetch, sample_commodity):
        prices = list(range(100, 600))
        mock_fetch.return_value = self._make_price_df(prices)

        signal, details = check_trend_signal(sample_commodity)
        assert signal is True
        assert details["latest_close"] > details["sma_50"]
        assert details["sma_50"] > details["sma_200"]

    @patch("cot.price_data.fetch_price_data")
    def test_downtrend_signal(self, mock_fetch, sample_commodity):
        prices = list(range(600, 100, -1))
        mock_fetch.return_value = self._make_price_df(prices)

        signal, details = check_trend_signal(sample_commodity)
        assert signal is False

    @patch("cot.price_data.fetch_price_data")
    def test_handles_fetch_error(self, mock_fetch, sample_commodity):
        mock_fetch.side_effect = ValueError("No data")

        signal, details = check_trend_signal(sample_commodity)
        assert signal is False
        assert "error" in details

    @patch("cot.price_data.fetch_price_data")
    def test_insufficient_data_for_sma200(self, mock_fetch, sample_commodity):
        prices = list(range(100, 250))
        mock_fetch.return_value = self._make_price_df(prices)

        signal, details = check_trend_signal(sample_commodity)
        assert signal is False
        assert details["sma_200"] is None
