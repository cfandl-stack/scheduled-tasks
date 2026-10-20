from unittest.mock import MagicMock, patch

from cot.config import Commodity, EmailConfig
from cot.email_alert import build_email_body, send_email
from cot.signals import Alert


def _make_alert(name: str, etf: str, combined: bool) -> Alert:
    return Alert(
        commodity=Commodity(name, "000000", "XX=F", etf),
        commercial_signal=combined,
        trend_signal=combined,
        combined_signal=combined,
        commercial_details={"current_value": 80000, "previous_max": 75000, "current_date": "2025-06-01", "weeks_available": 52},
        trend_details={"latest_close": 2500.0, "sma_50": 2400.0, "sma_200": 2200.0, "latest_date": "2025-06-01"},
    )


class TestBuildEmailBody:
    def test_contains_commodity_names(self):
        alerts = [_make_alert("Gold", "UGL", True)]
        html = build_email_body(alerts, alerts)
        assert "Gold" in html
        assert "UGL" in html

    def test_no_signals_message(self):
        alert = _make_alert("Gold", "UGL", False)
        html = build_email_body([], [alert])
        assert "No buy signals this week" in html
        assert "Gold" in html

    def test_contains_disclaimer(self):
        html = build_email_body([], [_make_alert("Gold", "UGL", False)])
        assert "Disclaimer" in html
        assert "not financial advice" in html

    def test_status_table_shows_all(self):
        alerts = [
            _make_alert("Gold", "UGL", True),
            _make_alert("Silver", "AGQ", False),
        ]
        html = build_email_body([alerts[0]], alerts)
        assert "Gold" in html
        assert "Silver" in html
        assert "BUY" in html

    def test_contains_signal_details(self):
        alert = _make_alert("Gold", "UGL", True)
        html = build_email_body([alert], [alert])
        assert "80,000" in html
        assert "75,000" in html
        assert "2500.0" in html


class TestSendEmail:
    @patch("cot.email_alert.smtplib.SMTP")
    def test_smtp_sequence(self, mock_smtp_class):
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        config = EmailConfig(
            smtp_server="smtp.test.com",
            smtp_port=587,
            sender_email="sender@test.com",
            sender_password="password123",
            recipient_email="recipient@test.com",
        )

        send_email(config, "Test Subject", "<html>Test</html>")

        mock_smtp_class.assert_called_once_with("smtp.test.com", 587)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("sender@test.com", "password123")
        mock_server.sendmail.assert_called_once()
