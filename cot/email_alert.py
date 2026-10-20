import logging
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from cot.config import HOLD_WEEKS, EmailConfig
from cot.signals import Alert

logger = logging.getLogger(__name__)


def build_email_body(actionable_alerts: list[Alert], all_alerts: list[Alert]) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    sell_date = (datetime.now() + timedelta(weeks=HOLD_WEEKS)).strftime("%Y-%m-%d")

    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; color: #333; max-width: 700px; margin: auto; }}
            h1 {{ color: #1a1a2e; border-bottom: 2px solid #e94560; padding-bottom: 10px; }}
            h2 {{ color: #1a1a2e; margin-top: 30px; }}
            .alert-box {{ background: #f0fff0; border-left: 4px solid #28a745; padding: 15px; margin: 15px 0; border-radius: 4px; }}
            .no-alert {{ background: #f8f9fa; border-left: 4px solid #6c757d; padding: 15px; margin: 15px 0; border-radius: 4px; }}
            table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
            th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
            th {{ background-color: #1a1a2e; color: white; }}
            tr:nth-child(even) {{ background-color: #f8f9fa; }}
            .yes {{ color: #28a745; font-weight: bold; }}
            .no {{ color: #dc3545; }}
            .buy {{ color: #28a745; font-weight: bold; font-size: 1.1em; }}
            .disclaimer {{ font-size: 0.8em; color: #888; margin-top: 30px; border-top: 1px solid #ddd; padding-top: 10px; }}
            .detail {{ font-size: 0.9em; color: #555; }}
        </style>
    </head>
    <body>
        <h1>CFTC COT Trading Alert — {today}</h1>
    """

    if actionable_alerts:
        html += f'<p class="buy">🔔 {len(actionable_alerts)} Buy Signal(s) detected!</p>'

        for alert in actionable_alerts:
            com = alert.commercial_details
            trend = alert.trend_details
            html += f"""
            <div class="alert-box">
                <h3>{alert.commodity.name}</h3>
                <p class="buy">→ BUY {alert.commodity.leveraged_etf} (2x Leveraged ETF)</p>
                <p><strong>Hold until:</strong> {sell_date} ({HOLD_WEEKS} weeks)</p>
                <table>
                    <tr><th colspan="2">Commercial Signal</th></tr>
                    <tr><td>Current Long Position</td><td><strong>{com.get('current_value', 'N/A'):,}</strong></td></tr>
                    <tr><td>52-Week Prior Max</td><td>{com.get('previous_max', 'N/A'):,}</td></tr>
                    <tr><td>COT Report Date</td><td>{com.get('current_date', 'N/A')}</td></tr>
                    <tr><th colspan="2">Trend Signal</th></tr>
                    <tr><td>Latest Close</td><td>${trend.get('latest_close', 'N/A')}</td></tr>
                    <tr><td>50-Day SMA</td><td>${trend.get('sma_50', 'N/A')}</td></tr>
                    <tr><td>200-Day SMA</td><td>${trend.get('sma_200', 'N/A')}</td></tr>
                </table>
            </div>
            """
    else:
        html += """
        <div class="no-alert">
            <p>No buy signals this week. All commodities were evaluated — none met both
            the commercial positioning and trend criteria simultaneously.</p>
        </div>
        """

    html += """
        <h2>Full Status Overview</h2>
        <table>
            <tr>
                <th>Commodity</th>
                <th>Commercial Signal</th>
                <th>Trend Signal</th>
                <th>Combined</th>
            </tr>
    """

    for alert in all_alerts:
        com_class = "yes" if alert.commercial_signal else "no"
        trend_class = "yes" if alert.trend_signal else "no"
        comb_class = "yes" if alert.combined_signal else "no"
        com_text = "✅ YES" if alert.commercial_signal else "❌ NO"
        trend_text = "✅ YES" if alert.trend_signal else "❌ NO"
        comb_text = "🟢 BUY" if alert.combined_signal else "—"

        html += f"""
            <tr>
                <td><strong>{alert.commodity.name}</strong></td>
                <td class="{com_class}">{com_text}</td>
                <td class="{trend_class}">{trend_text}</td>
                <td class="{comb_class}">{comb_text}</td>
            </tr>
        """

    html += """
        </table>
        <p class="disclaimer">
            <strong>Disclaimer:</strong> This is an automated informational alert, not financial advice.
            Past performance does not guarantee future results. Always do your own research before trading.
            <br>Data sources: CFTC Commitment of Traders Report, Yahoo Finance.
        </p>
    </body>
    </html>
    """
    return html


def send_email(config: EmailConfig, subject: str, html_body: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.sender_email
    msg["To"] = config.recipient_email
    msg.attach(MIMEText(html_body, "html"))

    logger.info("Sending email to %s via %s:%d", config.recipient_email, config.smtp_server, config.smtp_port)

    with smtplib.SMTP(config.smtp_server, config.smtp_port) as server:
        server.starttls()
        server.login(config.sender_email, config.sender_password)
        server.sendmail(config.sender_email, config.recipient_email, msg.as_string())

    logger.info("Email sent successfully")


def send_alert_email(
    config: EmailConfig,
    actionable_alerts: list[Alert],
    all_alerts: list[Alert],
) -> None:
    today = datetime.now().strftime("%Y-%m-%d")

    if actionable_alerts:
        names = ", ".join(a.commodity.name for a in actionable_alerts)
        subject = f"COT Alert: {len(actionable_alerts)} Buy Signal(s) — {names} — {today}"
    else:
        subject = f"COT Alert: No Signals — {today}"

    html_body = build_email_body(actionable_alerts, all_alerts)
    send_email(config, subject, html_body)
