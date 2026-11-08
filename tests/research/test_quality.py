import json
from datetime import date

import pandas as pd
import pytest

from research import prices, report


def _frame(closes, start="2026-01-01", spread=1.0):
    idx = pd.date_range(start, periods=len(closes), freq="D")
    c = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame({"High": c + spread, "Low": c - spread, "Close": c})


class TestStats:
    def test_levels(self):
        s = prices.stats(_frame(list(range(1, 251))))
        assert s["close"] == 250
        assert s["sma50"] == pytest.approx(225.5)
        assert s["sma200"] == pytest.approx(150.5)
        assert s["chg_1w"] == pytest.approx((250 / 245 - 1) * 100)
        assert s["atr14"] == pytest.approx(2.0)  # High-Low = 2, gaps of 1 stay inside
        assert s["high_52w"] == 251 and s["low_52w"] == 0

    def test_short_history_has_no_sma(self):
        s = prices.stats(_frame([10, 11, 12]))
        assert s["sma50"] is None and s["atr14"] is None and s["chg_1w"] is None

    def test_format_markets_skips_missing(self):
        text = prices.format_markets({"^GSPC": _frame([100.0] * 30)}, {"Acme (Insider-Kauf)": "ACME"})
        assert "S&P 500 [^GSPC]" in text and "ACME" not in text
        assert prices.format_markets({}) == ""


class TestReview:
    def test_target_hit_long(self):
        f = _frame([100, 100, 104, 112], spread=0.5)
        r = prices.review_idea({"symbol": "X", "direction": "long", "entry": 100, "stop": 95, "target": 110},
                               f, f.index[1].date())
        assert r["status"] == "Ziel erreicht"
        assert r["return_pct"] == pytest.approx(12.0)

    def test_stop_hit_short(self):
        f = _frame([100, 100, 103, 108], spread=0.5)
        r = prices.review_idea({"symbol": "X", "direction": "short", "entry": 100, "stop": 105, "target": 90},
                               f, f.index[1].date())
        assert r["status"] == "Stop erreicht"
        assert r["return_pct"] == pytest.approx(-8.0)

    def test_open_and_missing(self):
        f = _frame([100, 100, 101], spread=0.5)
        idea = {"symbol": "X", "direction": "long", "entry": 100, "stop": 90, "target": 120}
        assert prices.review_idea(idea, f, f.index[1].date())["status"] == "offen"
        assert prices.review_idea(idea, None, date(2026, 1, 1))["status"] == "keine Kursdaten"


class TestSplitIdeas:
    def test_extracts_and_strips_block(self):
        md = ("# Research Report — x\n\nText\n\n```json\n" + json.dumps({"ideas": [
            {"name": "Gold", "symbol": "GC=F", "direction": "long", "entry": 100, "stop": 95, "target": 110},
            {"symbol": "BAD", "direction": "long", "entry": 100, "stop": 99, "target": 101.5},
            {"symbol": "WRONG", "direction": "long", "entry": 100, "stop": 105, "target": 110},
            {"symbol": "NOPRICE", "direction": "short"},
        ]}) + "\n```\n")
        text, ideas = report.split_ideas(md)
        assert text == "# Research Report — x\n\nText"
        assert [i["symbol"] for i in ideas] == ["GC=F", "BAD"]
        assert ideas[0]["rr"] == 2.0

    def test_no_or_broken_block(self):
        assert report.split_ideas("# R\nText") == ("# R\nText", [])
        assert report.split_ideas("# R\n```json\n{kaputt}\n```") == ("# R", [])


class TestContextQuality:
    def test_rank_marks_extreme(self):
        assert "tiefster Wert der Historie" in report._rank([10, 20, 30, 4], 4)
        assert "Tage mit Wert <= aktuell: 2" in report._rank([10, 5, 30, 5], 5)
        assert report._rank([], 5) == ""

    def test_insider_aggregation_and_roles(self, tmp_path):
        trades = [
            {"ticker": "CRBG", "company": "Corebridge", "insider": "Nippon Life", "title": "10%",
             "value": 6e6, "price": 34.5, "trade_date": "2026-10-19", "delta_own": 0},
            {"ticker": "CRBG", "company": "Corebridge", "insider": "Nippon Life", "title": "10%",
             "value": 8e6, "price": 35.2, "trade_date": "2026-10-22", "delta_own": 0},
            {"ticker": "MSM", "company": "MSC", "insider": "Jacobson", "title": "Dir, 10%",
             "value": 2e6, "price": 115.9, "trade_date": "2026-10-23", "delta_own": 3, "cluster": True},
        ]
        (tmp_path / "insider.json").write_text(json.dumps({"window_days": 14, "trades": trades}), encoding="utf-8")
        ctx = report.build_market_context(str(tmp_path))
        assert ctx.count("CRBG (Corebridge)") == 1
        assert "$14.0M in 2 Käufen am 2026-10-19 bis 2026-10-22 zu $34.50–$35.20" in ctx
        assert "10%-Großaktionär" in ctx and "Board" in ctx
        # management/board first for price lookups, despite smaller value
        assert list(report.insider_symbols(str(tmp_path)).values()) == ["MSM", "CRBG"]

    def test_assemble_context_with_review(self, tmp_path):
        seen = {}

        def fake_fetch(symbols):
            seen["symbols"] = symbols
            return {"GC=F": _frame([100, 100, 104, 112], start="2026-11-01", spread=0.5)}

        history = [{"date": "2026-11-02", "ideas": [
            {"name": "Gold", "symbol": "GC=F", "direction": "long", "entry": 100, "stop": 95, "target": 110}]}]
        ctx = report.assemble_context(str(tmp_path), history, fetch=fake_fetch)
        assert "GC=F" in seen["symbols"] and "^GSPC" in seen["symbols"]
        assert "Gold [GC=F] Schluss 2026-11-04" in ctx
        assert "Rückblick: Trade-Ideen aus dem Report vom 2026-11-02" in ctx
        assert "Ziel erreicht" in ctx

    def test_assemble_context_survives_price_failure(self, tmp_path):
        def boom(symbols):
            raise RuntimeError("yahoo down")
        assert report.assemble_context(str(tmp_path), [], fetch=boom) == ""

    def test_prompt_contains_rules(self):
        prompt = report.build_prompt(date(2026, 11, 9), "ctx")
        for phrase in ("CRV", "ATR14", "konträr", "Rückblick Vorwoche", '"ideas"', "keine Idee"):
            assert phrase in prompt


class TestFetchRetry:
    def test_missing_symbols_are_retried_once(self, monkeypatch):
        calls = []

        def fake_fetch(symbols, period):
            calls.append(list(symbols))
            if len(calls) == 1:
                return {"^GSPC": _frame([1.0, 2.0])}
            return {"RAPP": _frame([3.0, 4.0])}

        monkeypatch.setattr(prices, "_fetch", fake_fetch)
        monkeypatch.setattr(prices, "_cache_ready", True)
        out = prices.fetch_history(["^GSPC", "RAPP", "NONE"])
        assert set(out) == {"^GSPC", "RAPP"}
        assert calls == [["^GSPC", "RAPP", "NONE"], ["RAPP", "NONE"]]

    def test_retry_failure_keeps_first_result(self, monkeypatch):
        def fake_fetch(symbols, period):
            if len(symbols) == 2:
                return {"A": _frame([1.0])}
            raise RuntimeError("yahoo down")

        monkeypatch.setattr(prices, "_fetch", fake_fetch)
        monkeypatch.setattr(prices, "_cache_ready", True)
        assert set(prices.fetch_history(["A", "B"])) == {"A"}
