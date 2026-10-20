import json
import re

import numpy as np
import pandas as pd
import pytest

from feargreed import main as fg_main
from feargreed.components import COMPONENTS
from feargreed.config import BREADTH_BASKET, HISTORY_DAYS, MARKET_TICKERS
from feargreed.data import extract_field
from feargreed.index import InsufficientDataError, build_feargreed, composite_series, write_json
from feargreed.components import MarketData
from tests.feargreed.conftest import make_download

SMALL_BASKET = BREADTH_BASKET[:12]


def _market_data(download=None, basket=SMALL_BASKET) -> MarketData:
    download = download or make_download()
    raw = download(MARKET_TICKERS)
    braw = download(basket)
    return MarketData(
        close=extract_field(raw, "Close", MARKET_TICKERS),
        basket_close=extract_field(braw, "Close", basket),
        basket_volume=extract_field(braw, "Volume", basket),
    )


@pytest.fixture(scope="module")
def result():
    return build_feargreed(_market_data())


class TestComposite:
    def test_mean_of_available_components(self):
        idx = pd.bdate_range("2025-01-01", periods=3)
        scores = {k: pd.Series([v] * 3, index=idx, dtype=float) for k, v in
                  {"a": 10, "b": 20, "c": 30, "d": 40}.items()}
        _, comp = composite_series(scores)
        assert comp.iloc[-1] == pytest.approx(25.0)

    def test_dates_with_too_few_components_dropped(self):
        idx = pd.bdate_range("2025-01-01", periods=10)
        scores = {k: pd.Series(50.0, index=idx) for k in "abc"}
        scores["d"] = pd.Series(50.0, index=idx[5:])
        _, comp = composite_series(scores)
        assert comp.index[0] == idx[5]

    def test_too_few_components_raises(self):
        idx = pd.bdate_range("2025-01-01", periods=3)
        with pytest.raises(InsufficientDataError):
            composite_series({k: pd.Series(50.0, index=idx) for k in "abc"})


class TestBuildFeargreed:
    def test_schema(self, result):
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", result["generated_at"])
        assert result["as_of"] == "2026-10-19"
        assert isinstance(result["score"], int) and 0 <= result["score"] <= 100
        for key in ("previous_close", "one_week_ago", "one_month_ago", "one_year_ago"):
            assert isinstance(result[key], int)
        assert result["rating"] in {"Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"}
        json.dumps(result)

    def test_components(self, result):
        comps = result["components"]
        assert [c["key"] for c in comps] == [c.key for c in COMPONENTS]
        for c in comps:
            assert set(c) >= {"key", "name", "name_de", "score", "rating", "rating_de",
                              "value", "value_label", "description_de"}
            assert 0 <= c["score"] <= 100
            assert isinstance(c["value"], float)

    def test_score_is_component_mean(self, result):
        mean = sum(c["score"] for c in result["components"]) / len(result["components"])
        assert abs(result["score"] - mean) <= 1

    def test_history(self, result):
        hist = result["history"]
        assert len(hist) == HISTORY_DAYS
        dates = [h["date"] for h in hist]
        assert dates == sorted(dates)
        assert hist[-1] == {"date": result["as_of"], "score": result["score"]}
        assert hist[-2]["score"] == result["previous_close"]
        assert all(0 <= h["score"] <= 100 for h in hist)

    def test_failed_component_excluded(self):
        md = _market_data(make_download(missing=("^VIX3M",)))
        res = build_feargreed(md)
        pc = next(c for c in res["components"] if c["key"] == "put_call")
        assert pc["score"] is None and "VIX3M" in pc["error"]
        ok = [c["score"] for c in res["components"] if c["score"] is not None]
        assert len(ok) == 6
        assert abs(res["score"] - sum(ok) / len(ok)) <= 1

    def test_too_many_failures_raises(self):
        md = _market_data(make_download(missing=("^GSPC", "^VIX", "IEF")))
        with pytest.raises(InsufficientDataError):
            build_feargreed(md)

    def test_short_history_gives_null_year_ago(self):
        res = build_feargreed(_market_data(make_download(n_days=360)))
        assert res["one_year_ago"] is None
        assert len(res["history"]) < HISTORY_DAYS

    def test_rally_is_greedy_and_selloff_fearful(self):
        n, shock = 600, 25
        idx = pd.bdate_range(end="2026-10-19", periods=n)
        rng = np.random.default_rng(3)
        base = np.exp(np.cumsum(rng.normal(0, 0.005, n)))
        jitter = rng.normal(0, 0.002, (n, 5))

        def md(direction: int):
            drift = np.ones(n)
            drift[-shock:] = np.exp(np.cumsum(np.full(shock, 0.01 * direction)))
            stocks = 100 * base * drift
            vix = 18 / drift ** 3
            close = pd.DataFrame({
                "^GSPC": stocks, "SPY": stocks, "HYG": 80 * base ** 0.3 * drift ** 0.3,
                "IEF": 100 * base ** 0.1, "^VIX": vix, "^VIX3M": np.full(n, 20.0),
            }, index=idx)
            basket = pd.DataFrame(stocks[:, None] * np.exp(jitter), index=idx, columns=list("ABCDE"))
            vol = pd.DataFrame(1000.0, index=idx, columns=list("ABCDE"))
            return MarketData(close, basket, vol)

        greedy = build_feargreed(md(+1))
        fearful = build_feargreed(md(-1))
        assert greedy["score"] >= 76 and greedy["rating"] == "Extreme Greed"
        assert fearful["score"] <= 24 and fearful["rating_de"] == "Extreme Angst"


class TestMain:
    def test_writes_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fg_main, "BREADTH_BASKET", SMALL_BASKET)
        monkeypatch.setattr(fg_main.data.yf, "download", make_download())
        path = tmp_path / "dashboard" / "data" / "feargreed.json"
        assert fg_main.main(str(path)) == 0
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data["components"]) == 7
        assert data["history"]

    def test_failure_keeps_existing_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fg_main, "BREADTH_BASKET", SMALL_BASKET)
        monkeypatch.setattr(
            fg_main.data.yf, "download", make_download(missing=("^GSPC", "^VIX", "^VIX3M", "SPY"))
        )
        path = tmp_path / "feargreed.json"
        path.write_text('{"old": true}')
        assert fg_main.main(str(path)) == 1
        assert json.loads(path.read_text()) == {"old": True}

    def test_download_exception_returns_1(self, tmp_path, monkeypatch):
        def boom(*args, **kwargs):
            raise ConnectionError("blocked")

        monkeypatch.setattr(fg_main.data.yf, "download", boom)
        assert fg_main.main(str(tmp_path / "x.json")) == 1
        assert not (tmp_path / "x.json").exists()

    def test_write_json_creates_dirs(self, tmp_path):
        path = tmp_path / "a" / "b" / "out.json"
        write_json({"score": 50, "rating_de": "Neutral"}, str(path))
        assert json.loads(path.read_text()) == {"score": 50, "rating_de": "Neutral"}
