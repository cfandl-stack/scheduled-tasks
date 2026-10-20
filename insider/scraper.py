from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

from insider.config import REQUEST_TIMEOUT, USER_AGENT, screener_url

logger = logging.getLogger(__name__)

HEADER_MAP = {
    "x": "x",
    "filing date": "filing_date",
    "trade date": "trade_date",
    "ticker": "ticker",
    "company name": "company",
    "company": "company",
    "insider name": "insider",
    "insider": "insider",
    "title": "title",
    "trade type": "trade_type",
    "price": "price",
    "qty": "qty",
    "owned": "owned",
    "δown": "delta_own",
    "delta own": "delta_own",
    "value": "value",
}

REQUIRED_COLUMNS = ("filing_date", "ticker", "insider", "trade_type", "value")


class FetchError(RuntimeError):
    pass


@dataclass
class Trade:
    filing_date: str
    trade_date: str
    ticker: str
    company: str
    insider: str
    title: str
    trade_type: str
    price: float | None
    qty: float | None
    owned: float | None
    delta_own: float | None
    value: float | None
    new_position: bool = False
    cluster: bool = False
    officer: bool = False
    reason: str = ""


def clean_number(text: str | None) -> float | None:
    """'$2.54' -> 2.54, '+10%' -> 10.0, '-$1,498,980' -> -1498980.0, 'New'/'' -> None."""
    if text is None:
        return None
    s = text.replace("\xa0", " ").strip()
    if not s or s.lower() in {"new", "n/a", "-"}:
        return None
    s = s.lstrip("<>")
    s = re.sub(r"[$,%\s]", "", s)
    if s.startswith("+"):
        s = s[1:]
    try:
        return float(s)
    except ValueError:
        return None


def _norm_header(text: str) -> str:
    return " ".join(text.replace("\xa0", " ").split()).lower()


def parse_screener_html(html: str) -> list[Trade]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("table.tinytable")
    if table is None:
        raise FetchError("Tabelle 'table.tinytable' nicht gefunden")

    header_cells = table.select("thead th") or table.select("tr th")
    columns = [HEADER_MAP.get(_norm_header(th.get_text()), None) for th in header_cells]
    missing = [c for c in REQUIRED_COLUMNS if c not in columns]
    if missing:
        raise FetchError(f"Unerwartete Tabellenstruktur, fehlende Spalten: {missing}")

    body = table.find("tbody") or table
    trades: list[Trade] = []
    for tr in body.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < len(columns):
            continue
        raw = {
            col: td.get_text(" ", strip=True).replace("\xa0", " ")
            for col, td in zip(columns, tds)
            if col
        }
        delta_raw = raw.get("delta_own", "")
        trades.append(
            Trade(
                filing_date=raw.get("filing_date", ""),
                trade_date=raw.get("trade_date", ""),
                ticker=raw.get("ticker", "").upper(),
                company=raw.get("company", ""),
                insider=raw.get("insider", ""),
                title=raw.get("title", ""),
                trade_type=raw.get("trade_type", ""),
                price=clean_number(raw.get("price")),
                qty=clean_number(raw.get("qty")),
                owned=clean_number(raw.get("owned")),
                delta_own=clean_number(delta_raw),
                value=clean_number(raw.get("value")),
                new_position=delta_raw.strip().lower() == "new",
            )
        )
    logger.info("Parsed %d rows from screener table", len(trades))
    return trades


def fetch_screener_html(url: str | None = None, session: requests.Session | None = None) -> str:
    url = url or screener_url()
    http = session or requests.Session()
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        resp = http.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise FetchError(f"Abruf von openinsider fehlgeschlagen: {exc}") from exc
    return resp.text


def fetch_trades(url: str | None = None, session: requests.Session | None = None) -> list[Trade]:
    return parse_screener_html(fetch_screener_html(url, session))
