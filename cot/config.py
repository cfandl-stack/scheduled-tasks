import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Commodity:
    name: str
    cftc_code: str
    futures_ticker: str
    leveraged_etf: str


COMMODITIES: list[Commodity] = [
    Commodity("Gold", "088691", "GC=F", "UGL"),
    Commodity("Silver", "084691", "SI=F", "AGQ"),
    Commodity("Crude Oil (WTI)", "067651", "CL=F", "UCO"),
    Commodity("E-mini S&P 500", "13874A", "ES=F", "SSO"),
    Commodity("10-Year Treasury", "043602", "ZN=F", "UBT"),
    Commodity("Natural Gas", "023651", "NG=F", "BOIL"),
]

COT_LOOKBACK_WEEKS = 52
SMA_SHORT_PERIOD = 50
SMA_LONG_PERIOD = 200
PRICE_HISTORY_PERIOD = "2y"
HOLD_WEEKS = 4


@dataclass
class EmailConfig:
    smtp_server: str
    smtp_port: int
    sender_email: str
    sender_password: str
    recipient_email: str


def load_email_config() -> EmailConfig:
    sender = os.environ.get("SENDER_EMAIL")
    password = os.environ.get("SENDER_PASSWORD")
    recipient = os.environ.get("RECIPIENT_EMAIL")

    if not sender or not password or not recipient:
        missing = [
            name
            for name, val in [
                ("SENDER_EMAIL", sender),
                ("SENDER_PASSWORD", password),
                ("RECIPIENT_EMAIL", recipient),
            ]
            if not val
        ]
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    return EmailConfig(
        smtp_server=os.environ.get("SMTP_SERVER") or "smtp.gmail.com",
        smtp_port=int(os.environ.get("SMTP_PORT") or "587"),
        sender_email=sender,
        sender_password=password,
        recipient_email=recipient,
    )
