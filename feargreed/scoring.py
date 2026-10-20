import math

import numpy as np
import pandas as pd

from feargreed.config import PERCENTILE_MIN_PERIODS, PERCENTILE_WINDOW, RATING_BANDS, RatingBand


def round_half_up(x: float) -> int:
    return int(math.floor(x + 0.5))


def _last_value_rank(window: np.ndarray) -> float:
    window = window[~np.isnan(window)]
    n = len(window)
    if n < 2:
        return np.nan
    x = window[-1]
    less = np.sum(window < x)
    equal = np.sum(window == x) - 1
    return (less + 0.5 * equal) / (n - 1) * 100.0


def percentile_score(
    series: pd.Series,
    window: int = PERCENTILE_WINDOW,
    min_periods: int = PERCENTILE_MIN_PERIODS,
    invert: bool = False,
) -> pd.Series:
    """Rank of each value within its trailing window, scaled 0 (lowest) to 100 (highest)."""
    scores = series.rolling(window, min_periods=min_periods).apply(_last_value_rank, raw=True)
    if invert:
        scores = 100.0 - scores
    return scores.dropna()


def rating_for(score: float) -> RatingBand:
    s = round_half_up(score)
    for band in RATING_BANDS:
        if s <= band.upper:
            return band
    return RATING_BANDS[-1]
