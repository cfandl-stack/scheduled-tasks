"""Persistent raw daily values: {component_key: {"YYYY-MM-DD": value}}."""
import json
import logging
import math
import os
from datetime import date, timedelta
from typing import Any

from futuresfg.config import RAW_RETENTION_DAYS

logger = logging.getLogger(__name__)

RawStore = dict[str, dict[str, Any]]


def load(path: str) -> RawStore:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        logger.warning("Raw store %s unreadable, starting empty: %s", path, exc)
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: dict(v) for k, v in data.items() if isinstance(v, dict)}


def _finite(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(value) and all(_finite(v) for v in value.values())
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def merge(store: RawStore, key: str, fresh: dict[str, Any], before: date) -> RawStore:
    """Overlay fresh values on the stored ones (fresh wins); only complete days < `before`."""
    cutoff = before.isoformat()
    series = dict(store.get(key, {}))
    for d, v in fresh.items():
        if d < cutoff and _finite(v):
            series[d] = v
    out = dict(store)
    out[key] = dict(sorted(series.items()))
    return out


def prune(store: RawStore, today: date, keep_days: int = RAW_RETENTION_DAYS) -> RawStore:
    first = (today - timedelta(days=keep_days)).isoformat()
    return {k: {d: v for d, v in s.items() if d >= first} for k, s in store.items()}


def last_date(store: RawStore, key: str) -> date | None:
    series = store.get(key) or {}
    return date.fromisoformat(max(series)) if series else None


def count_since(store: RawStore, key: str, since: date) -> int:
    first = since.isoformat()
    return sum(1 for d in store.get(key, {}) if d >= first)


def _compact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _compact(v) for k, v in value.items()}
    return float(f"{value:.10g}")


def dumps(store: RawStore) -> str:
    """One line per day so that daily commits produce small diffs."""
    blocks = []
    for key in sorted(store):
        rows = [
            f"    {json.dumps(d)}: {json.dumps(_compact(v), separators=(', ', ': '))}"
            for d, v in sorted(store[key].items())
        ]
        body = "{\n" + ",\n".join(rows) + "\n  }" if rows else "{}"
        blocks.append(f"  {json.dumps(key)}: {body}")
    return "{\n" + ",\n".join(blocks) + "\n}\n"


def atomic_write(path: str, text: str) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def save(store: RawStore, path: str) -> None:
    atomic_write(path, dumps(store))
