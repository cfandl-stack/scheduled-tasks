import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from insider import main as insider_main
from insider.config import screener_url
from insider.filters import apply_filters, is_officer, mark_clusters
from insider.json_output import build_insider_json, write_insider_json
from insider.scraper import FetchError, clean_number, fetch_screener_html, parse_screener_html

FIXTURE = Path(__file__).parent / "fixtures" / "screener.html"


@pytest.fixture
def html():
    return FIXTURE.read_text(encoding="utf-8")


@pytest.fixture
def trades(html):
    return parse_screener_html(html)


class TestCleanNumber:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("$2.54", 2.54),
            ("+10%", 10.0),
            ("$1,498,980", 1498980.0),
            ("+$2,408,384", 2408384.0),
            ("-$5,000,000", -5000000.0),
            ("+950,000", 950000.0),
            (">999%", 999.0),
            ("New", None),
            ("", None),
            (None, None),
            ("abc", None),
        ],
    )
    def test_values(self, raw, expected):
        assert clean_number(raw) == expected


class TestParse:
    def test_row_count(self, trades):
        assert len(trades) == 7

    def test_first_row_fields(self, trades):
        t = trades[0]
        assert t.filing_date == "2026-04-03 14:14:25"
        assert t.trade_date == "2026-04-01"
        assert t.ticker == "RPAY"
        assert t.company == "Repay Holdings Corp"
        assert t.insider == "Forager Fund, L.P."
        assert t.title == "10%"
        assert t.trade_type == "P - Purchase"
        assert t.price == 2.54
        assert t.qty == 950000.0
        assert t.owned == 10192937.0
        assert t.delta_own == 10.0
        assert t.value == 2408384.0

    def test_new_position(self, trades):
        jane = next(t for t in trades if t.insider == "Doe Jane")
        assert jane.delta_own is None
        assert jane.new_position is True

    def test_missing_table_raises(self):
        with pytest.raises(FetchError):
            parse_screener_html("<html><body>Rate limited</body></html>")

    def test_unexpected_headers_raise(self):
        html = '<table class="tinytable"><thead><tr><th>Foo</th></tr></thead></table>'
        with pytest.raises(FetchError):
            parse_screener_html(html)


class TestFilters:
    def test_officer_roles(self):
        assert is_officer("CEO")
        assert is_officer("Pres, COO")
        assert is_officer("10%")
        assert is_officer("Dir")
        assert not is_officer("VP Sales")
        assert not is_officer("Director of Ops")

    def test_cluster_detection(self, trades):
        assert mark_clusters(trades) == {"ACME"}
        assert all(t.cluster == (t.ticker == "ACME") for t in trades)

    def test_cluster_needs_distinct_insiders(self, trades):
        acme = [t for t in trades if t.ticker == "ACME"]
        acme[1].insider = acme[0].insider
        assert mark_clusters(acme) == set()

    def test_apply_filters(self, trades):
        kept = apply_filters(trades)
        tickers = [t.ticker for t in kept]
        assert "TINY" not in tickers
        assert "SELL" not in tickers
        assert tickers[:2] == ["RPAY", "BIGC"]
        assert sorted(tickers[2:]) == ["ACME", "ACME", "GROW"]

    def test_reasons(self, trades):
        kept = {(t.ticker, t.insider): t for t in apply_filters(trades)}
        assert kept[("RPAY", "Forager Fund, L.P.")].reason == "Wert $2,408,384, Position +10.0%"
        assert kept[("BIGC", "Roe Richard")].reason == "Wert $455,000"
        assert kept[("GROW", "Lee Ann")].reason == "Position +20.0%"
        assert kept[("ACME", "Smith John")].reason == "Cluster (2 Insider)"
        assert kept[("ACME", "Doe Jane")].reason == "Neue Position, Cluster (2 Insider)"
        assert kept[("BIGC", "Roe Richard")].officer is True


class TestJson:
    def test_schema(self, trades):
        data = build_insider_json(apply_filters(trades), "http://x", 14)
        assert data["generated_at"].endswith("Z")
        assert data["window_days"] == 14
        assert data["count"] == len(data["trades"]) == 5
        first = data["trades"][0]
        for key in ("filing_date", "trade_date", "ticker", "company", "insider", "title",
                    "trade_type", "price", "qty", "owned", "delta_own", "value", "cluster", "reason"):
            assert key in first
        assert isinstance(first["value"], float)
        values = [t["value"] for t in data["trades"]]
        assert values == sorted(values, reverse=True)

    def test_write_creates_dirs(self, tmp_path, trades):
        path = tmp_path / "dashboard" / "data" / "insider.json"
        write_insider_json(build_insider_json(apply_filters(trades), "u", 14), str(path))
        loaded = json.loads(path.read_text())
        assert loaded["count"] == 5
        jane = next(t for t in loaded["trades"] if t["insider"] == "Doe Jane")
        assert jane["delta_own"] is None
        assert jane["cluster"] is True


class TestFetch:
    def test_url_params(self):
        url = screener_url(14)
        assert url.startswith("http://openinsider.com/screener?")
        assert "xp=1" in url and "fd=14" in url and "cnt=" in url

    def test_sends_browser_user_agent(self):
        session = MagicMock()
        session.get.return_value.text = "<html/>"
        fetch_screener_html("http://example", session=session)
        headers = session.get.call_args.kwargs["headers"]
        assert headers["User-Agent"].startswith("Mozilla/5.0")

    def test_http_error_raises_fetch_error(self):
        session = MagicMock()
        session.get.side_effect = requests.ConnectionError("blocked")
        with pytest.raises(FetchError):
            fetch_screener_html("http://example", session=session)


class TestMain:
    def test_success_writes_json(self, tmp_path, html):
        out = tmp_path / "data" / "insider.json"
        with patch("insider.scraper.fetch_screener_html", return_value=html):
            assert insider_main.main(str(out)) == 0
        assert json.loads(out.read_text())["count"] == 5

    def test_failure_does_not_overwrite(self, tmp_path):
        out = tmp_path / "insider.json"
        out.write_text('{"old": true}')
        with patch("insider.scraper.fetch_screener_html", side_effect=FetchError("403")):
            assert insider_main.main(str(out)) == 1
        assert out.read_text() == '{"old": true}'

    def test_bad_markup_does_not_overwrite(self, tmp_path):
        out = tmp_path / "insider.json"
        out.write_text('{"old": true}')
        with patch("insider.scraper.fetch_screener_html", return_value="<html>captcha</html>"):
            assert insider_main.main(str(out)) == 1
        assert out.read_text() == '{"old": true}'
        assert list(tmp_path.iterdir()) == [out]
