import logging
import os
import sys

from research.report import (
    MODEL,
    assemble_context,
    build_entry,
    generate_report,
    load_history,
    openrouter_sender,
    split_ideas,
    write_outputs,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    try:
        logger.info("Starting research report (model %s)", MODEL)
        context = assemble_context(history=load_history())
        logger.info("Context: %d chars", len(context))
        report, model = generate_report(openrouter_sender(os.environ["OPENROUTER_API_KEY"]), context=context)
        markdown, ideas = split_ideas(report)
        entry = build_entry(markdown, model=model, ideas=ideas)
        write_outputs(entry)
        logger.info("Wrote report.md and dashboard/data/research*.json (%d chars, %d ideas)", len(markdown), len(ideas))
        return 0
    except Exception:
        logger.exception("Fatal error in research report")
        return 1


if __name__ == "__main__":
    sys.exit(main())
