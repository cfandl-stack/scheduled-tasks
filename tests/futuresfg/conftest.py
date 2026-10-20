from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pytest

from futuresfg import config
from futuresfg.components import COMPONENTS, Component, Source

TODAY = date(2026, 10, 20)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(config, "PAGE_PAUSE", 0)

    def blocked(*args, **kwargs):
        raise AssertionError("network access in tests")

    monkeypatch.setattr("futuresfg.http._request", blocked)


def daily_values(n_days: int, seed: int = 0, end: date = TODAY - timedelta(days=1), make=None) -> dict:
    rng = np.random.default_rng(seed)
    out = {}
    for i in range(n_days):
        d = (end - timedelta(days=n_days - 1 - i)).isoformat()
        x = float(rng.normal())
        out[d] = make(x, rng) if make else x
    return out


def _raw_for(key: str, n_days: int, seed: int) -> dict:
    makers = {
        "liquidations": lambda x, rng: {"long": float(rng.uniform(1e7, 3e8)), "short": float(rng.uniform(1e7, 3e8))},
        "rsi_vol": lambda x, rng: {"rsi": 50 + 15 * x, "vol": float(rng.uniform(20, 80))},
        "dxy": lambda x, rng: {"level": 120 + x, "change": x},
    }
    return daily_values(n_days, seed, make=makers.get(key))


def fake_components(n_days: int = 500, overrides: dict | None = None) -> list[Component]:
    """Real component metadata with in-memory sources (no network)."""
    overrides = overrides or {}
    out = []
    for i, comp in enumerate(COMPONENTS):
        if comp.key in overrides:
            sources = overrides[comp.key]
        else:
            data = _raw_for(comp.key, n_days, seed=i)
            sources = (Source("Fake", lambda start, data=data: data),)
        out.append(replace(comp, sources=tuple(sources)))
    return out
