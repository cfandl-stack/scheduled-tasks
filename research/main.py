import logging
import os
import sys

from research.report import MODEL, build_entry, generate_report, openrouter_sender, write_outputs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    try:
        logger.info("Starting research report (model %s)", MODEL)
        markdown = generate_report(openrouter_sender(os.environ["OPENROUTER_API_KEY"]))
        entry = build_entry(markdown)
        write_outputs(entry)
        logger.info("Wrote report.md and dashboard/data/research*.json (%d chars)", len(markdown))
        return 0
    except Exception:
        logger.exception("Fatal error in research report")
        return 1


if __name__ == "__main__":
    sys.exit(main())
