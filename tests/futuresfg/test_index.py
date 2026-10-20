from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from futuresfg.components import COMPONENTS, Component, Source
from futuresfg.index import (
    InsufficientDataError,
    build_futuresfg,
    collect,
    component_scores,
    composite_series,
    fetch_component,
    fetch_start,
    smoothed,
)
from tests.futuresfg.conftest import TODAY, daily_values, fake_components

COMP = {c.key: c for c in COMPONENTS}


def _days(values, end=date(2026, 10, 19)):
    n = len(values)
    return {(end - timedelta(days=n - 1 - i)).isoformat(): v for i, v in enumerate(values)}


class TestComponentScores:
    def test_new_high_vs_own_history_scores_100(self):
        s = component_scores(COMP["funding"], _days(list(range(100))))
        assert s.iloc[-1] == pytest.approx(100.0)

    def test_inverted_component(self):
        s = component_scores(COMP["vix"], _days(list(range(100))))
        assert s.iloc[-1] == pytest.approx(0.0)

    def test_min_history_60_days(self):
        s = component_scores(COMP["funding"], _days(list(range(59))))
        assert s.empty
        s = component_scores(COMP["funding"], _days(list(range(60))))
        assert len(s) == 1

    def test_window_is_365_calendar_days(self):
        # A huge value 366 days ago no longer counts; one 364 days ago does.
        old = _days([1000.0] + [0.0] * 365 + [10.0])
        assert component_scores(COMP["funding"], old).iloc[-1] == pytest.approx(100.0)
        recent = _days([1000.0] + [0.0] * 363 + [10.0])
        assert component_scores(COMP["funding"], recent).iloc[-1] < 100.0

    def test_rsi_vol_averages_rsi_and_inverted_vol(self):
        raw = _days([{"rsi": float(i), "vol": float(i)} for i in range(100)])
        # Highest RSI (100) and highest vol (inverted → 0) average to 50.
        assert component_scores(COMP["rsi_vol"], raw).iloc[-1] == pytest.approx(50.0)

    def test_liquidations_short_share(self):
        raw = _days([{"long": 100.0, "short": float(i)} for i in range(100)])
        assert component_scores(COMP["liquidations"], raw).iloc[-1] == pytest.approx(100.0)

    def test_dxy_scores_inverted_change(self):
        raw = _days([{"level": 120.0, "change": float(i)} for i in range(100)])
        assert component_scores(COMP["dxy"], raw).iloc[-1] == pytest.approx(0.0)


class TestComposite:
    def _scores(self, values: dict, periods=10):
        idx = pd.date_range("2026-10-10", periods=periods, freq="D")
        return {k: pd.Series(float(v), index=idx) for k, v in values.items()}

    def test_equal_weight_mean(self):
        scores = self._scores({k: v for k, v in zip("abcde", [10, 20, 30, 40, 50])})
        _, comp = composite_series(scores, {}, date(2026, 10, 19))
        assert comp.iloc[-1] == pytest.approx(30.0)

    def test_missing_component_uses_remaining(self):
        scores = self._scores({k: 50 for k in "abcde"})
        scores["f"] = pd.Series(dtype=float)
        _, comp = composite_series(scores, {}, date(2026, 10, 19))
        assert comp.iloc[-1] == pytest.approx(50.0)

    def test_stale_score_carried_forward_up_to_limit(self):
        scores = self._scores({k: 50 for k in "abcd"})
        scores["e"] = pd.Series(100.0, index=pd.date_range("2026-10-10", periods=5, freq="D"))  # ends 10-14
        frame, comp = composite_series(scores, {"e": 3}, date(2026, 10, 19))
        assert frame.loc["2026-10-17", "e"] == 100.0
        assert pd.isna(frame.loc["2026-10-18", "e"])
        assert comp.index[-1] == pd.Timestamp("2026-10-17")

    def test_too_few_components(self):
        with pytest.raises(InsufficientDataError):
            composite_series(self._scores({k: 50 for k in "abcd"}), {}, date(2026, 10, 19))

    def test_seven_day_mean(self):
        idx = pd.date_range("2026-10-01", periods=10, freq="D")
        s = smoothed(pd.Series(np.arange(10, dtype=float), index=idx))
        assert s.iloc[-1] == pytest.approx(np.mean(np.arange(3, 10)))
        assert s.iloc[0] == 0.0


class TestFetching:
    def _comp(self, *sources):
        return Component(key="x", group="futures", name_de="X", description_de="", sources=sources,
                         label=str, value=float)

    def test_first_failing_source_falls_back(self):
        def boom(start):
            raise ConnectionError("451 Unavailable For Legal Reasons")

        comp = self._comp(Source("A", boom), Source("B", lambda s: {"2026-10-19": 1.0}), Source("C", boom))
        data, source, error = fetch_component(comp, date(2026, 1, 1))
        assert (data, source, error) == ({"2026-10-19": 1.0}, "B", None)

    def test_empty_result_counts_as_failure(self):
        comp = self._comp(Source("A", lambda s: {}), Source("B", lambda s: {"2026-10-19": 2.0}))
        assert fetch_component(comp, date(2026, 1, 1))[1] == "B"

    def test_all_sources_fail(self):
        def boom(start):
            raise ValueError("x")

        data, source, error = fetch_component(self._comp(Source("A", boom), Source("B", boom)), date(2026, 1, 1))
        assert data == {} and source is None and "A" in error and "B" in error

    def test_fetch_start_bootstrap_then_incremental(self):
        assert fetch_start({}, "a", TODAY) == TODAY - timedelta(days=420)
        full = {"a": daily_values(400)}
        assert fetch_start(full, "a", TODAY) == TODAY - timedelta(days=11)


@pytest.fixture(scope="module")
def result():
    comps = fake_components()
    store, sources, errors = collect({}, TODAY, comps)
    return build_futuresfg(store, sources, errors, TODAY, comps)


class TestBuild:
    def test_as_of_is_last_complete_day(self, result):
        assert result["as_of"] == "2026-10-19"

    def test_index_is_seven_day_mean(self, result):
        hist = result["history"]
        assert len(hist) == 365
        assert hist[-1]["index"] == result["index"]
        assert hist[-1]["daily"] == result["today"]
        mean7 = np.mean([h["daily"] for h in hist[-7:]])
        assert abs(result["index"] - mean7) <= 1

    def test_comparisons(self, result):
        hist = {h["date"]: h["index"] for h in result["history"]}
        assert result["previous_day"] == hist["2026-10-18"]
        assert result["one_week_ago"] == hist["2026-10-12"]
        assert result["one_month_ago"] == hist["2026-09-19"]

    def test_rating_band(self, result):
        from feargreed.scoring import rating_for
        band = rating_for(result["index"])
        assert (result["rating"], result["rating_de"]) == (band.rating, band.rating_de)

    def test_group_layout(self, result):
        assert [g["key"] for g in result["groups"]] == ["futures", "flows"]
        assert [g["name_de"] for g in result["groups"]] == ["Futures-Markt", "Flows und Makro"]
        assert [c["key"] for g in result["groups"] for c in g["components"]] == [c.key for c in COMPONENTS]
        for g in result["groups"]:
            assert len(g["components"]) == 5

    def test_component_schema(self, result):
        for g in result["groups"]:
            for c in g["components"]:
                assert {"key", "name_de", "score", "value", "value_label", "description_de",
                        "source", "history_days", "error"} <= set(c)
                assert isinstance(c["score"], int) and 0 <= c["score"] <= 100
                assert isinstance(c["value_label"], str) and c["value_label"]
                assert c["source"] == "Fake" and c["error"] is None
                assert c["history_days"] == 365


class TestMissingComponents:
    def _build(self, overrides):
        comps = fake_components(overrides=overrides)
        store, sources, errors = collect({}, TODAY, comps)
        result = build_futuresfg(store, sources, errors, TODAY, comps)
        return {c["key"]: c for g in result["groups"] for c in g["components"]}, result

    def test_failed_component_reported_as_missing(self):
        def blocked(start):
            raise ConnectionError("403")

        comps, result = self._build({"etf_flows": (Source("Farside", blocked),)})
        etf = comps["etf_flows"]
        assert etf["score"] is None and etf["value_label"] == "–" and etf["source"] is None
        assert "Farside" in etf["error"]
        assert result["components_scored"] == 9

    def test_short_history_collects(self):
        short = daily_values(5, seed=3, make=lambda x, rng: {"long": 2e8, "short": 5e7})
        comps, _ = self._build({"liquidations": (Source("OKX", lambda s: short),)})
        liq = comps["liquidations"]
        assert liq["score"] is None
        assert liq["error"] == "Sammle Historie (5/60 Tage)"
        assert liq["value_label"] == "200 / 50 Mio. $" and liq["source"] == "OKX"

    def test_stored_history_reused_when_fetch_fails(self):
        comps = fake_components()
        store, _, _ = collect({}, TODAY, comps)

        def boom(start):
            raise ConnectionError("down")

        failing = fake_components(overrides={"vix": (Source("Yahoo", boom),)})
        store2, sources, errors = collect(store, TODAY, failing)
        assert store2["vix"] == store["vix"]
        result = build_futuresfg(store2, sources, errors, TODAY, failing)
        vix = next(c for g in result["groups"] for c in g["components"] if c["key"] == "vix")
        assert vix["score"] is not None and vix["source"] is None

    def test_fewer_than_five_components_fails(self):
        def boom(start):
            raise ConnectionError("down")

        keys = [c.key for c in COMPONENTS][:6]
        with pytest.raises(InsufficientDataError):
            self._build({k: (Source("X", boom),) for k in keys})
