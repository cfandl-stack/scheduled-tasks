import logging
import sys
from datetime import UTC, date, datetime

from futuresfg import store as raw_store
from futuresfg.components import COMPONENTS, Component
from futuresfg.config import OUTPUT_PATH, RAW_PATH
from futuresfg.index import InsufficientDataError, build_futuresfg, collect, write_json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main(
    output_path: str = OUTPUT_PATH,
    raw_path: str = RAW_PATH,
    components: list[Component] = COMPONENTS,
    today: date | None = None,
) -> int:
    today = today or datetime.now(UTC).date()
    try:
        logger.info("Starting Futures Fear & Greed (today %s UTC)", today)
        store, sources, errors = collect(raw_store.load(raw_path), today, components)
        result = build_futuresfg(store, sources, errors, today, components)
        raw_store.save(store, raw_path)
        write_json(result, output_path)
        logger.info(
            "Wrote %s: index %d (%s), daily %d, as of %s, %d/%d components",
            output_path, result["index"], result["rating"], result["today"], result["as_of"],
            result["components_scored"], len(components),
        )
        return 0
    except InsufficientDataError as exc:
        logger.error("Not enough data, keeping existing JSON: %s", exc)
        return 1
    except Exception:
        logger.exception("Fatal error in Futures Fear & Greed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
