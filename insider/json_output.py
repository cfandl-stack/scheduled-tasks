from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime

from insider.scraper import Trade

TRADE_FIELDS = (
    "filing_date", "trade_date", "ticker", "company", "insider", "title", "trade_type",
    "price", "qty", "owned", "delta_own", "value", "cluster", "officer", "reason",
)


def trade_to_dict(trade: Trade) -> dict:
    return {f: getattr(trade, f) for f in TRADE_FIELDS}


def build_insider_json(trades: list[Trade], source: str, window_days: int) -> dict:
    return {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": source,
        "window_days": window_days,
        "count": len(trades),
        "trades": [trade_to_dict(t) for t in trades],
    }


def write_insider_json(data: dict, path: str) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
