import logging
import sys

import pandas as pd

from feargreed import data
from feargreed.components import MarketData
from feargreed.config import BREADTH_BASKET, MARKET_TICKERS, OUTPUT_PATH
from feargreed.index import InsufficientDataError, build_feargreed, write_json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def load_market_data() -> MarketData:
    try:
        raw = data.download(MARKET_TICKERS)
        close = data.extract_field(raw, "Close", MARKET_TICKERS)
    except Exception:
        logger.exception("Market download failed")
        close = pd.DataFrame()

    try:
        raw = data.download(BREADTH_BASKET)
        basket_close = data.extract_field(raw, "Close", BREADTH_BASKET)
        basket_volume = data.extract_field(raw, "Volume", BREADTH_BASKET)
        logger.info("Basket: %d/%d tickers with data", basket_close.shape[1], len(BREADTH_BASKET))
    except Exception:
        logger.exception("Basket download failed")
        basket_close = basket_volume = pd.DataFrame()

    return MarketData(close=close, basket_close=basket_close, basket_volume=basket_volume)


def main(output_path: str = OUTPUT_PATH) -> int:
    try:
        logger.info("Starting Fear & Greed Index")
        result = build_feargreed(load_market_data())
        write_json(result, output_path)
        logger.info(
            "Wrote %s: %d (%s) as of %s", output_path, result["score"], result["rating"], result["as_of"]
        )
        return 0
    except InsufficientDataError as exc:
        logger.error("Not enough data, keeping existing JSON: %s", exc)
        return 1
    except Exception:
        logger.exception("Fatal error in Fear & Greed Index")
        return 1


if __name__ == "__main__":
    sys.exit(main())
