from cot.config import Commodity
from cot.json_output import build_cot_json
from cot.signals import Alert


def _alert(name: str, etf: str, commercial: bool, trend: bool,
           com: dict | None = None, tr: dict | None = None) -> Alert:
    commodity = Commodity(name, "000000", "XX=F", etf)
    return Alert(
        commodity=commodity,
        commercial_signal=commercial,
        trend_signal=trend,
        combined_signal=commercial and trend,
        commercial_details=com or {},
        trend_details=tr or {},
    )


class TestBuildCotJson:
    def test_top_level_keys_present(self):
        result = build_cot_json([], [])
        for key in ("generated_at", "report_date", "signal_count", "buy_signals", "full_status"):
            assert key in result

    def test_signal_count_matches_actionable(self):
        actionable = [_alert("Crude Oil (WTI)", "UCO", True, True)]
        result = build_cot_json(actionable, actionable)
        assert result["signal_count"] == 1

    def test_zero_signals(self):
        result = build_cot_json([], [_alert("Gold", "UGL", False, False)])
        assert result["signal_count"] == 0
        assert result["buy_signals"] == []

    def test_buy_signal_commodity_and_etf(self):
        alert = _alert("Crude Oil (WTI)", "UCO", True, True)
        result = build_cot_json([alert], [alert])
        sig = result["buy_signals"][0]
        assert sig["commodity"] == "Crude Oil (WTI)"
        assert sig["etf"] == "UCO"

    def test_buy_signal_commercial_fields(self):
        cd = {"current_value": 933442, "previous_max": 903255, "current_date": "2026-05-05"}
        alert = _alert("Crude Oil (WTI)", "UCO", True, True, com=cd)
        result = build_cot_json([alert], [alert])
        com = result["buy_signals"][0]["commercial"]
        assert com["current_long"] == 933442
        assert com["prior_52w_max"] == 903255
        assert com["report_date"] == "2026-05-05"

    def test_buy_signal_trend_fields(self):
        td = {"latest_close": 95.42, "sma_50": 94.48, "sma_200": 69.79}
        alert = _alert("Crude Oil (WTI)", "UCO", True, True, tr=td)
        result = build_cot_json([alert], [alert])
        tr = result["buy_signals"][0]["trend"]
        assert tr["latest_close"] == 95.42
        assert tr["sma50"] == 94.48
        assert tr["sma200"] == 69.79

    def test_full_status_length_matches_all_alerts(self):
        alerts = [
            _alert("Gold", "UGL", False, False),
            _alert("Crude Oil (WTI)", "UCO", True, True),
        ]
        result = build_cot_json([alerts[1]], alerts)
        assert len(result["full_status"]) == 2

    def test_full_status_signals_correct(self):
        alerts = [
            _alert("Gold", "UGL", False, False),
            _alert("Crude Oil (WTI)", "UCO", True, True),
        ]
        result = build_cot_json([alerts[1]], alerts)
        gold = next(s for s in result["full_status"] if s["commodity"] == "Gold")
        assert gold["commercial_signal"] is False
        assert gold["trend_signal"] is False
        assert gold["combined"] is False
        oil = next(s for s in result["full_status"] if s["commodity"] == "Crude Oil (WTI)")
        assert oil["combined"] is True

    def test_empty_actionable_no_buy_signals(self):
        all_alerts = [_alert("Gold", "UGL", False, False)]
        result = build_cot_json([], all_alerts)
        assert result["signal_count"] == 0
        assert result["buy_signals"] == []

    def test_generated_at_parseable(self):
        from datetime import datetime
        result = build_cot_json([], [])
        datetime.strptime(result["generated_at"], "%Y-%m-%dT%H:%M:%SZ")

    def test_hold_until_is_4_weeks_from_today(self):
        from datetime import date, timedelta
        result = build_cot_json([_alert("Crude Oil (WTI)", "UCO", True, True)], [])
        hold = result["buy_signals"][0]["hold_until"]
        expected = (date.today() + timedelta(weeks=4)).isoformat()
        assert hold == expected
