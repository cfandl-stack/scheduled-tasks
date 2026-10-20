import logging
import sys

from cot.config import load_email_config
from cot.email_alert import send_alert_email
from cot.json_output import write_cot_json
from cot.signals import evaluate_all_commodities, get_actionable_alerts

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    try:
        logger.info("Starting COT trading alert")

        try:
            email_config = load_email_config()
            logger.info("Email config loaded (recipient: %s)", email_config.recipient_email)
        except ValueError as e:
            email_config = None
            logger.warning("Email disabled: %s", e)

        all_alerts = evaluate_all_commodities()
        actionable = get_actionable_alerts(all_alerts)

        logger.info(
            "Evaluation complete: %d/%d commodities triggered",
            len(actionable),
            len(all_alerts),
        )

        if email_config:
            send_alert_email(email_config, actionable, all_alerts)

        write_cot_json(actionable, all_alerts)
        logger.info("Wrote dashboard/data/cot.json (%d buy signals)", len(actionable))

        logger.info("Done")
        return 0

    except Exception:
        logger.exception("Fatal error in COT alert script")
        return 1


if __name__ == "__main__":
    sys.exit(main())
