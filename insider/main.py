import logging
import sys

from insider.config import OUTPUT_PATH, WINDOW_DAYS, screener_url
from insider.filters import apply_filters
from insider.json_output import build_insider_json, write_insider_json
from insider.scraper import fetch_trades

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main(output_path: str = OUTPUT_PATH) -> int:
    url = screener_url(WINDOW_DAYS)
    try:
        logger.info("Fetching openinsider screener: %s", url)
        trades = fetch_trades(url)
        if not trades:
            raise RuntimeError("Screener lieferte keine Zeilen")
        kept = apply_filters(trades)
        logger.info("%d/%d purchases passed filters", len(kept), len(trades))
        write_insider_json(build_insider_json(kept, url, WINDOW_DAYS), output_path)
        logger.info("Wrote %s", output_path)
        return 0
    except Exception:
        logger.exception("Insider screener failed; existing JSON left untouched")
        return 1


if __name__ == "__main__":
    sys.exit(main())
