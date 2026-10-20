from __future__ import annotations

import re
from collections import defaultdict

from insider.config import (
    CLUSTER_MIN_INSIDERS,
    MIN_DELTA_OWN_PCT,
    MIN_VALUE_USD,
    OFFICER_ROLES,
)
from insider.scraper import Trade

_ROLE_PATTERNS = [re.compile(rf"(?<![A-Za-z]){re.escape(r)}(?![A-Za-z])", re.IGNORECASE) for r in OFFICER_ROLES]


def is_purchase(trade: Trade) -> bool:
    return trade.trade_type.strip().upper().startswith("P")


def is_officer(title: str) -> bool:
    return any(p.search(title or "") for p in _ROLE_PATTERNS)


def mark_clusters(trades: list[Trade], min_insiders: int = CLUSTER_MIN_INSIDERS) -> set[str]:
    insiders: dict[str, set[str]] = defaultdict(set)
    for t in trades:
        insiders[t.ticker].add(t.insider.strip().lower())
    clusters = {ticker for ticker, names in insiders.items() if len(names) >= min_insiders}
    for t in trades:
        t.cluster = t.ticker in clusters
    return clusters


def materiality_reason(
    trade: Trade,
    min_value: float = MIN_VALUE_USD,
    min_delta: float = MIN_DELTA_OWN_PCT,
) -> str:
    parts: list[str] = []
    if trade.value is not None and trade.value >= min_value:
        parts.append(f"Wert ${trade.value:,.0f}")
    if trade.new_position:
        parts.append("Neue Position")
    elif trade.delta_own is not None and trade.delta_own >= min_delta:
        parts.append(f"Position +{trade.delta_own:.1f}%")
    return ", ".join(parts)


def apply_filters(trades: list[Trade]) -> list[Trade]:
    """Keep purchases that are material (value/ΔOwn) or part of a cluster; sorted by value desc."""
    purchases = [t for t in trades if is_purchase(t)]
    mark_clusters(purchases)

    kept: list[Trade] = []
    for t in purchases:
        t.officer = is_officer(t.title)
        reason = materiality_reason(t)
        if t.cluster:
            n = len({p.insider.strip().lower() for p in purchases if p.ticker == t.ticker})
            reason = ", ".join(filter(None, [reason, f"Cluster ({n} Insider)"]))
        if not reason:
            continue
        t.reason = reason
        kept.append(t)

    kept.sort(key=lambda t: t.value if t.value is not None else float("-inf"), reverse=True)
    return kept
