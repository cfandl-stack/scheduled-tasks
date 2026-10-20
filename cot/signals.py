import logging
from dataclasses import dataclass

from cot.config import COMMODITIES, Commodity
from cot.cot_data import check_commercial_signal, fetch_cot_data
from cot.price_data import check_trend_signal

logger = logging.getLogger(__name__)


@dataclass
class Alert:
    commodity: Commodity
    commercial_signal: bool
    trend_signal: bool
    combined_signal: bool
    commercial_details: dict
    trend_details: dict


def evaluate_all_commodities() -> list[Alert]:
    logger.info("Evaluating %d commodities", len(COMMODITIES))
    cot_df = fetch_cot_data()

    alerts = []
    for commodity in COMMODITIES:
        logger.info("Processing %s", commodity.name)

        try:
            com_signal, com_details = check_commercial_signal(cot_df, commodity)
        except ValueError as e:
            logger.error("Commercial signal failed for %s: %s", commodity.name, e)
            com_signal = False
            com_details = {"error": str(e)}

        trend_signal, trend_details = check_trend_signal(commodity)

        combined = com_signal and trend_signal

        alerts.append(
            Alert(
                commodity=commodity,
                commercial_signal=com_signal,
                trend_signal=trend_signal,
                combined_signal=combined,
                commercial_details=com_details,
                trend_details=trend_details,
            )
        )

        if combined:
            logger.info("BUY SIGNAL: %s → %s", commodity.name, commodity.leveraged_etf)

    return alerts


def get_actionable_alerts(alerts: list[Alert]) -> list[Alert]:
    return [a for a in alerts if a.combined_signal]
