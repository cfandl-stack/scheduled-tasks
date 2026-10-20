import numpy as np
import pandas as pd
import pytest

from feargreed.scoring import percentile_score, rating_for, round_half_up


def _series(values):
    return pd.Series(values, index=pd.bdate_range("2024-01-01", periods=len(values)), dtype=float)


class TestPercentileScore:
    def test_new_high_scores_100(self):
        s = percentile_score(_series(range(1, 11)), window=5, min_periods=5)
        assert (s == 100.0).all()

    def test_new_low_scores_0(self):
        s = percentile_score(_series(range(10, 0, -1)), window=5, min_periods=5)
        assert (s == 0.0).all()

    def test_median_scores_50(self):
        s = percentile_score(_series([1, 2, 4, 5, 3]), window=5, min_periods=5)
        assert s.iloc[-1] == pytest.approx(50.0)

    def test_ties_get_mid_rank(self):
        s = percentile_score(_series([5, 5, 5, 5, 5]), window=5, min_periods=5)
        assert s.iloc[-1] == pytest.approx(50.0)

    def test_only_trailing_window_counts(self):
        # Early huge values fall out of the window.
        s = percentile_score(_series([100, 100, 1, 2, 3, 4]), window=4, min_periods=4)
        assert s.iloc[-1] == pytest.approx(100.0)

    def test_min_periods_drops_early_rows(self):
        s = percentile_score(_series(range(10)), window=5, min_periods=3)
        assert len(s) == 8

    def test_ignores_nan(self):
        s = percentile_score(_series([1, np.nan, 2, 3, 4]), window=5, min_periods=3)
        assert s.iloc[-1] == pytest.approx(100.0)

    def test_inversion(self):
        values = _series([3, 1, 4, 1, 5, 9, 2, 6])
        normal = percentile_score(values, window=5, min_periods=5)
        inverted = percentile_score(values, window=5, min_periods=5, invert=True)
        pd.testing.assert_series_equal(inverted, 100.0 - normal)

    def test_scores_bounded(self):
        rng = np.random.default_rng(1)
        s = percentile_score(_series(rng.normal(size=400)), window=252, min_periods=126)
        assert s.between(0, 100).all()


class TestRating:
    @pytest.mark.parametrize(
        "score,rating,rating_de",
        [
            (0, "Extreme Fear", "Extreme Angst"),
            (24, "Extreme Fear", "Extreme Angst"),
            (24.4, "Extreme Fear", "Extreme Angst"),
            (25, "Fear", "Angst"),
            (44, "Fear", "Angst"),
            (45, "Neutral", "Neutral"),
            (55, "Neutral", "Neutral"),
            (56, "Greed", "Gier"),
            (75, "Greed", "Gier"),
            (76, "Extreme Greed", "Extreme Gier"),
            (100, "Extreme Greed", "Extreme Gier"),
        ],
    )
    def test_bands(self, score, rating, rating_de):
        band = rating_for(score)
        assert band.rating == rating
        assert band.rating_de == rating_de

    def test_round_half_up(self):
        assert round_half_up(44.5) == 45
        assert round_half_up(44.49) == 44
        assert round_half_up(0.5) == 1
