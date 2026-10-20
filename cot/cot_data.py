import logging
from datetime import datetime

import pandas as pd
from cot_reports import cot_year

from cot.config import COT_LOOKBACK_WEEKS, Commodity

logger = logging.getLogger(__name__)


def fetch_cot_data(year_current: int | None = None) -> pd.DataFrame:
    year = year_current or datetime.now().year
    logger.info("Fetching COT data for %d and %d", year - 1, year)

    df_prev = cot_year(year - 1, cot_report_type="legacy_fut", store_txt=False)
    df_curr = cot_year(year, cot_report_type="legacy_fut", store_txt=False)

    df = pd.concat([df_prev, df_curr], ignore_index=True)
    df["As of Date in Form YYYY-MM-DD"] = pd.to_datetime(
        df["As of Date in Form YYYY-MM-DD"]
    )
    return df


def get_commercial_long_series(cot_df: pd.DataFrame, commodity: Commodity) -> pd.Series:
    mask = cot_df["CFTC Contract Market Code"] == commodity.cftc_code
    filtered = cot_df.loc[mask].copy()
    filtered = filtered.sort_values("As of Date in Form YYYY-MM-DD")
    filtered = filtered.set_index("As of Date in Form YYYY-MM-DD")
    return filtered["Commercial Positions-Long (All)"]


def check_commercial_signal(
    cot_df: pd.DataFrame,
    commodity: Commodity,
    lookback_weeks: int = COT_LOOKBACK_WEEKS,
) -> tuple[bool, dict]:
    series = get_commercial_long_series(cot_df, commodity)

    if len(series) < 2:
        raise ValueError(
            f"Not enough COT data for {commodity.name} "
            f"(code {commodity.cftc_code}): only {len(series)} weeks"
        )

    recent = series.iloc[-lookback_weeks:] if len(series) >= lookback_weeks else series
    current_value = int(recent.iloc[-1])
    previous_max = int(recent.iloc[:-1].max())
    signal = current_value > previous_max

    details = {
        "current_value": current_value,
        "previous_max": previous_max,
        "current_date": str(recent.index[-1].date()),
        "weeks_available": len(recent),
    }

    logger.info(
        "%s commercial signal: %s (current=%d, prev_max=%d)",
        commodity.name,
        signal,
        current_value,
        previous_max,
    )
    return signal, details
