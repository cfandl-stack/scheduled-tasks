import json
import logging
import math
import os
from datetime import UTC, datetime, timedelta

import pandas as pd

from feargreed.components import COMPONENTS, Component, MarketData
from feargreed.config import HISTORY_DAYS, MAX_FFILL_DAYS, MIN_COMPONENTS
from feargreed.scoring import percentile_score, rating_for, round_half_up

logger = logging.getLogger(__name__)


class InsufficientDataError(RuntimeError):
    pass


def score_components(
    md: MarketData, components: list[Component] = COMPONENTS
) -> tuple[dict[str, pd.Series], dict[str, pd.Series], dict[str, str]]:
    raws: dict[str, pd.Series] = {}
    scores: dict[str, pd.Series] = {}
    errors: dict[str, str] = {}
    for comp in components:
        try:
            raw = comp.compute(md)
            sc = percentile_score(raw, invert=comp.invert)
            if sc.empty:
                raise ValueError("insufficient history")
            raws[comp.key], scores[comp.key] = raw, sc
            logger.info("%s: score %.1f on %s", comp.key, sc.iloc[-1], sc.index[-1].date())
        except Exception as exc:
            logger.warning("Component %s failed: %s", comp.key, exc)
            errors[comp.key] = f"{type(exc).__name__}: {exc}"
    return raws, scores, errors


def composite_series(scores: dict[str, pd.Series], min_components: int = MIN_COMPONENTS) -> tuple[pd.DataFrame, pd.Series]:
    if len(scores) < min_components:
        raise InsufficientDataError(f"Only {len(scores)} components available (need {min_components})")
    frame = pd.concat(scores, axis=1, sort=True).ffill(limit=MAX_FFILL_DAYS)
    count = frame.notna().sum(axis=1)
    composite = frame.mean(axis=1).where(count >= min_components).dropna()
    if composite.empty:
        raise InsufficientDataError("No date with enough component scores")
    return frame, composite


def _value_on_or_before(series: pd.Series, when: pd.Timestamp) -> int | None:
    past = series.loc[:when]
    if past.empty:
        return None
    return round_half_up(past.iloc[-1])


def build_feargreed(md: MarketData, components: list[Component] = COMPONENTS) -> dict:
    raws, scores, errors = score_components(md, components)
    frame, composite = composite_series(scores)
    as_of = composite.index[-1]

    comp_out = []
    for comp in components:
        entry = {"key": comp.key, "name": comp.name, "name_de": comp.name_de}
        score = frame.at[as_of, comp.key] if comp.key in frame.columns else math.nan
        if comp.key in errors or pd.isna(score):
            entry.update({
                "score": None,
                "error": errors.get(comp.key, f"no data for {as_of.date()}"),
                "description_de": comp.description_de,
            })
        else:
            value = float(raws[comp.key].loc[:as_of].iloc[-1])
            band = rating_for(score)
            entry.update({
                "score": round_half_up(score),
                "rating": band.rating,
                "rating_de": band.rating_de,
                "value": round(value, 4),
                "value_label": comp.label(value),
                "description_de": comp.description_de,
            })
        comp_out.append(entry)

    ok = sum(1 for c in comp_out if c["score"] is not None)
    if ok < MIN_COMPONENTS:
        raise InsufficientDataError(f"Only {ok} components current on {as_of.date()}")

    score = round_half_up(composite.iloc[-1])
    band = rating_for(score)
    history = composite.iloc[-HISTORY_DAYS:]
    first = composite.index[0]
    year_ago = as_of - timedelta(days=365)

    return {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": as_of.date().isoformat(),
        "score": score,
        "rating": band.rating,
        "rating_de": band.rating_de,
        "previous_close": round_half_up(composite.iloc[-2]) if len(composite) > 1 else None,
        "one_week_ago": _value_on_or_before(composite, as_of - timedelta(days=7)),
        "one_month_ago": _value_on_or_before(composite, as_of - timedelta(days=30)),
        "one_year_ago": _value_on_or_before(composite, year_ago) if first <= year_ago else None,
        "components": comp_out,
        "history": [
            {"date": d.date().isoformat(), "score": round_half_up(v)} for d, v in history.items()
        ],
    }


def write_json(data: dict, path: str) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)
