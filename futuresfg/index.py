import json
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd

from feargreed.scoring import percentile_score, rating_for, round_half_up
from futuresfg import store as raw_store
from futuresfg.components import COMPONENTS, GROUPS, Component
from futuresfg.config import (
    BOOTSTRAP_DAYS,
    BOOTSTRAP_MIN_ENTRIES,
    DEFAULT_MAX_STALE_DAYS,
    HISTORY_DAYS,
    MAX_AS_OF_LAG_DAYS,
    MIN_COMPONENTS,
    PERCENTILE_MIN_PERIODS,
    PERCENTILE_WINDOW,
    REFRESH_OVERLAP_DAYS,
    SMOOTHING_DAYS,
)

logger = logging.getLogger(__name__)


class InsufficientDataError(RuntimeError):
    pass


# ─── Fetching ─────────────────────────────────────────────

def fetch_start(store: raw_store.RawStore, key: str, today: date) -> date:
    """Full bootstrap while history is short, otherwise only the last few days."""
    bootstrap = today - timedelta(days=BOOTSTRAP_DAYS)
    last = raw_store.last_date(store, key)
    if last is None or raw_store.count_since(store, key, today - timedelta(days=365)) < BOOTSTRAP_MIN_ENTRIES:
        return bootstrap
    return max(bootstrap, last - timedelta(days=REFRESH_OVERLAP_DAYS))


def fetch_component(comp: Component, start: date) -> tuple[dict[str, Any], str | None, str | None]:
    """Try each source in order; first non-empty result wins."""
    errors = []
    for src in comp.sources:
        try:
            data = src.fetch(start)
            if not data:
                raise ValueError("empty result")
            logger.info("%s: %d days from %s (%s .. %s)", comp.key, len(data), src.name, min(data), max(data))
            return data, src.name, None
        except Exception as exc:
            logger.warning("%s: source %s failed: %s: %s", comp.key, src.name, type(exc).__name__, exc)
            errors.append(f"{src.name}: {type(exc).__name__}")
    return {}, None, "Keine Quelle erreichbar (" + ", ".join(errors) + ")"


def collect(
    store: raw_store.RawStore, today: date, components: list[Component] = COMPONENTS
) -> tuple[raw_store.RawStore, dict[str, str | None], dict[str, str]]:
    sources: dict[str, str | None] = {}
    errors: dict[str, str] = {}
    for comp in components:
        data, source, error = fetch_component(comp, fetch_start(store, comp.key, today))
        sources[comp.key] = source
        if error:
            errors[comp.key] = error
        store = raw_store.merge(store, comp.key, data, before=today)
    return raw_store.prune(store, today), sources, errors


# ─── Scoring ──────────────────────────────────────────────

def raw_series(series: dict[str, Any]) -> pd.Series:
    s = pd.Series(list(series.values()), index=pd.DatetimeIndex(list(series.keys())), dtype=object)
    return s.sort_index()


def component_scores(comp: Component, series: dict[str, Any]) -> pd.Series:
    """Daily score: mean of the component's metric percentiles vs. their own trailing 365 days."""
    if not series:
        return pd.Series(dtype=float)
    raw = raw_series(series)
    parts = []
    for metric in comp.metrics:
        values = pd.to_numeric(raw.map(metric.extract), errors="coerce").dropna().astype(float)
        if values.empty:
            return pd.Series(dtype=float)
        parts.append(percentile_score(
            values, window=PERCENTILE_WINDOW, min_periods=PERCENTILE_MIN_PERIODS, invert=metric.invert
        ))
    frame = pd.concat(parts, axis=1).dropna()
    return frame.mean(axis=1)


def composite_series(
    scores: dict[str, pd.Series], max_stale: dict[str, int], end: date, min_components: int = MIN_COMPONENTS
) -> tuple[pd.DataFrame, pd.Series]:
    """Equal-weight mean per calendar day; stale scores carry forward up to max_stale days."""
    available = {k: s for k, s in scores.items() if not s.empty}
    if len(available) < min_components:
        raise InsufficientDataError(f"Only {len(available)} components with scores (need {min_components})")
    first = min(s.index[0] for s in available.values())
    calendar = pd.date_range(first, pd.Timestamp(end), freq="D")
    frame = pd.DataFrame(index=calendar)
    for key, s in available.items():
        limit = max_stale.get(key, DEFAULT_MAX_STALE_DAYS)
        s = s.reindex(calendar)
        frame[key] = s.ffill(limit=limit) if limit > 0 else s
    count = frame.notna().sum(axis=1)
    composite = frame.mean(axis=1).where(count >= min_components).dropna()
    if composite.empty:
        raise InsufficientDataError("No day with enough component scores")
    return frame, composite


def smoothed(composite: pd.Series, days: int = SMOOTHING_DAYS) -> pd.Series:
    return composite.rolling(f"{days}D", min_periods=1).mean()


def _on_or_before(series: pd.Series, when: pd.Timestamp) -> int | None:
    past = series.loc[:when]
    return round_half_up(past.iloc[-1]) if not past.empty else None


def _latest_raw(series: dict[str, Any], as_of: pd.Timestamp) -> tuple[str, Any] | None:
    limit = as_of.date().isoformat()
    dates = [d for d in series if d <= limit]
    if not dates:
        return None
    d = max(dates)
    return d, series[d]


def _component_entry(
    comp: Component, series: dict[str, Any], score: float, as_of: pd.Timestamp,
    source: str | None, fetch_error: str | None,
) -> dict:
    window_start = (as_of - pd.Timedelta(days=364)).date().isoformat()
    history_days = sum(1 for d in series if window_start <= d <= as_of.date().isoformat())
    latest = _latest_raw(series, as_of)
    value = label = value_date = None
    if latest is not None:
        value_date, raw = latest
        try:
            v = comp.value(raw)
            value = round(v, 6) if v is not None else None
            label = comp.label(raw)
        except Exception as exc:
            logger.warning("%s: cannot format %r: %s", comp.key, raw, exc)

    error = None
    if pd.isna(score):
        if latest is None:
            error = fetch_error or "Keine Daten"
        elif history_days < PERCENTILE_MIN_PERIODS:
            error = f"Sammle Historie ({history_days}/{PERCENTILE_MIN_PERIODS} Tage)"
        else:
            error = fetch_error or f"Keine aktuellen Daten (letzter Wert {value_date})"

    return {
        "key": comp.key,
        "name_de": comp.name_de,
        "score": None if pd.isna(score) else round_half_up(score),
        "value": value,
        "value_label": label or "–",
        "value_date": value_date,
        "description_de": comp.description_de,
        "source": source,
        "history_days": history_days,
        "error": error,
    }


def build_futuresfg(
    store: raw_store.RawStore,
    sources: dict[str, str | None],
    errors: dict[str, str],
    today: date,
    components: list[Component] = COMPONENTS,
) -> dict:
    yesterday = today - timedelta(days=1)
    scores = {c.key: component_scores(c, store.get(c.key, {})) for c in components}
    for key, s in scores.items():
        if not s.empty:
            logger.info("%s: score %.1f on %s", key, s.iloc[-1], s.index[-1].date())
    frame, composite = composite_series(scores, {c.key: c.max_stale_days for c in components}, yesterday)
    as_of = composite.index[-1]
    if as_of.date() < yesterday - timedelta(days=MAX_AS_OF_LAG_DAYS):
        raise InsufficientDataError(f"Latest composite {as_of.date()} is stale")

    index_series = smoothed(composite)
    groups = []
    for key, name_de in GROUPS:
        entries = []
        for comp in (c for c in components if c.group == key):
            score = frame.at[as_of, comp.key] if comp.key in frame.columns else float("nan")
            entries.append(_component_entry(
                comp, store.get(comp.key, {}), score, as_of, sources.get(comp.key), errors.get(comp.key)
            ))
        groups.append({"key": key, "name_de": name_de, "components": entries})

    ok = sum(1 for g in groups for c in g["components"] if c["score"] is not None)
    if ok < MIN_COMPONENTS:
        raise InsufficientDataError(f"Only {ok} components scored on {as_of.date()}")

    index = round_half_up(index_series.iloc[-1])
    band = rating_for(index)
    history_from = as_of - pd.Timedelta(days=HISTORY_DAYS - 1)
    return {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": as_of.date().isoformat(),
        "index": index,
        "today": round_half_up(composite.iloc[-1]),
        "rating": band.rating,
        "rating_de": band.rating_de,
        "previous_day": _on_or_before(index_series, as_of - pd.Timedelta(days=1)),
        "one_week_ago": _on_or_before(index_series, as_of - pd.Timedelta(days=7)),
        "one_month_ago": _on_or_before(index_series, as_of - pd.Timedelta(days=30)),
        "components_scored": ok,
        "groups": groups,
        "history": [
            {"date": d.date().isoformat(), "daily": round_half_up(composite[d]), "index": round_half_up(v)}
            for d, v in index_series.loc[history_from:].items()
        ],
    }


def write_json(data: Any, path: str) -> None:
    raw_store.atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
