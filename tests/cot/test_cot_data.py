import pandas as pd
import pytest

from cot.config import Commodity
from cot.cot_data import check_commercial_signal, get_commercial_long_series


@pytest.fixture
def sample_commodity():
    return Commodity("Gold", "088691", "GC=F", "UGL")


@pytest.fixture
def sample_cot_df():
    dates = pd.date_range("2025-01-07", periods=55, freq="7D")
    rows = []
    for i, date in enumerate(dates):
        rows.append(
            {
                "CFTC Contract Market Code": "088691",
                "As of Date in Form YYYY-MM-DD": date,
                "Commercial Positions-Long (All)": 50000 + i * 100,
                "Market and Exchange Names": "GOLD - COMMODITY EXCHANGE INC.",
            }
        )
        rows.append(
            {
                "CFTC Contract Market Code": "084691",
                "As of Date in Form YYYY-MM-DD": date,
                "Commercial Positions-Long (All)": 30000 + i * 50,
                "Market and Exchange Names": "SILVER - COMMODITY EXCHANGE INC.",
            }
        )
    return pd.DataFrame(rows)


class TestGetCommercialLongSeries:
    def test_filters_by_cftc_code(self, sample_cot_df, sample_commodity):
        series = get_commercial_long_series(sample_cot_df, sample_commodity)
        assert len(series) == 55

    def test_sorted_chronologically(self, sample_cot_df, sample_commodity):
        series = get_commercial_long_series(sample_cot_df, sample_commodity)
        assert series.index.is_monotonic_increasing

    def test_correct_values(self, sample_cot_df, sample_commodity):
        series = get_commercial_long_series(sample_cot_df, sample_commodity)
        assert series.iloc[0] == 50000
        assert series.iloc[-1] == 50000 + 54 * 100


class TestCheckCommercialSignal:
    def test_signal_true_when_new_high(self, sample_cot_df, sample_commodity):
        signal, details = check_commercial_signal(sample_cot_df, sample_commodity)
        assert signal is True
        assert details["current_value"] > details["previous_max"]

    def test_signal_false_when_not_new_high(self, sample_cot_df, sample_commodity):
        mask = (
            (sample_cot_df["CFTC Contract Market Code"] == "088691")
            & (sample_cot_df["As of Date in Form YYYY-MM-DD"] == sample_cot_df["As of Date in Form YYYY-MM-DD"].max())
        )
        sample_cot_df.loc[mask, "Commercial Positions-Long (All)"] = 40000
        signal, details = check_commercial_signal(sample_cot_df, sample_commodity)
        assert signal is False

    def test_signal_false_when_equal_to_max(self, sample_cot_df, sample_commodity):
        mask = (
            (sample_cot_df["CFTC Contract Market Code"] == "088691")
            & (sample_cot_df["As of Date in Form YYYY-MM-DD"] == sample_cot_df["As of Date in Form YYYY-MM-DD"].max())
        )
        prev_max = sample_cot_df.loc[
            sample_cot_df["CFTC Contract Market Code"] == "088691",
            "Commercial Positions-Long (All)",
        ].iloc[-2]
        sample_cot_df.loc[mask, "Commercial Positions-Long (All)"] = prev_max
        signal, _ = check_commercial_signal(sample_cot_df, sample_commodity)
        assert signal is False

    def test_raises_on_insufficient_data(self, sample_commodity):
        df = pd.DataFrame(
            [
                {
                    "CFTC Contract Market Code": "088691",
                    "As of Date in Form YYYY-MM-DD": pd.Timestamp("2025-01-07"),
                    "Commercial Positions-Long (All)": 50000,
                }
            ]
        )
        with pytest.raises(ValueError, match="Not enough COT data"):
            check_commercial_signal(df, sample_commodity)

    def test_details_dict_keys(self, sample_cot_df, sample_commodity):
        _, details = check_commercial_signal(sample_cot_df, sample_commodity)
        assert "current_value" in details
        assert "previous_max" in details
        assert "current_date" in details
        assert "weeks_available" in details
