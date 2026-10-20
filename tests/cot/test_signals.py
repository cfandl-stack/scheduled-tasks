from cot.config import Commodity
from cot.signals import Alert, get_actionable_alerts


def _make_alert(name: str, commercial: bool, trend: bool) -> Alert:
    commodity = Commodity(name, "000000", "XX=F", "XXX")
    return Alert(
        commodity=commodity,
        commercial_signal=commercial,
        trend_signal=trend,
        combined_signal=commercial and trend,
        commercial_details={},
        trend_details={},
    )


class TestGetActionableAlerts:
    def test_returns_only_combined_true(self):
        alerts = [
            _make_alert("A", True, True),
            _make_alert("B", True, False),
            _make_alert("C", False, True),
            _make_alert("D", False, False),
        ]
        result = get_actionable_alerts(alerts)
        assert len(result) == 1
        assert result[0].commodity.name == "A"

    def test_empty_when_no_signals(self):
        alerts = [
            _make_alert("A", True, False),
            _make_alert("B", False, True),
        ]
        assert get_actionable_alerts(alerts) == []

    def test_all_triggered(self):
        alerts = [
            _make_alert("A", True, True),
            _make_alert("B", True, True),
        ]
        assert len(get_actionable_alerts(alerts)) == 2

    def test_empty_input(self):
        assert get_actionable_alerts([]) == []
