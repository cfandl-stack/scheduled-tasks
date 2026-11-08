"""Kursdaten (yfinance) für den Research Report: Marktüberblick und Rückblick auf frühere Trade-Ideen."""
from __future__ import annotations

import logging
import math
from datetime import date

import pandas as pd

from feargreed.data import download, extract_field

logger = logging.getLogger(__name__)

# Anzeigename -> Yahoo-Finance-Symbol
MARKETS: dict[str, str] = {
    "S&P 500": "^GSPC",
    "Nasdaq 100": "^NDX",
    "DAX": "^GDAXI",
    "VIX": "^VIX",
    "US 10J-Rendite (%)": "^TNX",
    "US-Staatsanleihen 20J+ ETF": "TLT",
    "Dollar-Index": "DX-Y.NYB",
    "Gold": "GC=F",
    "Silber": "SI=F",
    "WTI Rohöl": "CL=F",
    "Bitcoin": "BTC-USD",
    "Ethereum": "ETH-USD",
}
PERIOD = "1y"
FIELDS = ("High", "Low", "Close")


def fetch_history(symbols: list[str], period: str = PERIOD) -> dict[str, pd.DataFrame]:
    """Daily High/Low/Close per symbol; symbols without data are left out."""
    symbols = list(dict.fromkeys(s for s in symbols if s))
    if not symbols:
        return {}
    df = download(symbols, period=period)
    fields = {f: extract_field(df, f, symbols) for f in FIELDS}
    out: dict[str, pd.DataFrame] = {}
    for s in symbols:
        if s not in fields["Close"].columns:
            logger.warning("No price data for %s", s)
            continue
        frame = pd.DataFrame({f: fields[f][s] if s in fields[f].columns else float("nan") for f in FIELDS})
        frame = frame.dropna(subset=["Close"])
        if not frame.empty:
            out[s] = frame
    return out


def _pct(a: float, b: float) -> float | None:
    return (a / b - 1) * 100 if b and not math.isnan(b) else None


def stats(frame: pd.DataFrame) -> dict:
    close = frame["Close"]
    last = float(close.iloc[-1])
    prev_close = close.shift(1)
    tr = pd.concat([
        frame["High"] - frame["Low"],
        (frame["High"] - prev_close).abs(),
        (frame["Low"] - prev_close).abs(),
    ], axis=1).max(axis=1, skipna=True)
    atr = tr.rolling(14).mean().iloc[-1] if len(tr) >= 15 else float("nan")
    year = frame.iloc[-252:]
    return {
        "date": frame.index[-1].date().isoformat(),
        "close": last,
        "chg_1w": _pct(last, float(close.iloc[-6])) if len(close) > 5 else None,
        "chg_1m": _pct(last, float(close.iloc[-22])) if len(close) > 21 else None,
        "sma50": float(close.iloc[-50:].mean()) if len(close) >= 50 else None,
        "sma200": float(close.iloc[-200:].mean()) if len(close) >= 200 else None,
        "atr14": None if math.isnan(atr) else float(atr),
        "high_52w": float(year["High"].max()) if year["High"].notna().any() else None,
        "low_52w": float(year["Low"].min()) if year["Low"].notna().any() else None,
    }


def _num(v: float | None) -> str:
    if v is None:
        return "–"
    return f"{v:,.2f}" if abs(v) < 100_000 else f"{v:,.0f}"


def _chg(v: float | None) -> str:
    return "–" if v is None else f"{v:+.1f}%"


def format_line(label: str, symbol: str, s: dict) -> str:
    atr = s["atr14"]
    atr_pct = f" ({atr / s['close'] * 100:.1f}% vom Kurs)" if atr else ""
    return (f"  - {label} [{symbol}] Schluss {s['date']}: {_num(s['close'])} | 1W {_chg(s['chg_1w'])}"
            f" | 1M {_chg(s['chg_1m'])} | SMA50 {_num(s['sma50'])} | SMA200 {_num(s['sma200'])}"
            f" | ATR14 {_num(atr)}{atr_pct} | 52W {_num(s['low_52w'])}–{_num(s['high_52w'])}")


def format_markets(history: dict[str, pd.DataFrame], extra: dict[str, str] | None = None) -> str:
    """Text block with key levels; `extra` maps label -> symbol (e.g. insider tickers)."""
    items = {**MARKETS, **(extra or {})}
    lines = []
    for label, sym in items.items():
        frame = history.get(sym)
        if frame is None or frame.empty:
            continue
        try:
            lines.append(format_line(label, sym, stats(frame)))
        except Exception:
            logger.exception("Could not compute stats for %s", sym)
    if not lines:
        return ""
    return ("Kursdaten (Yahoo Finance, Tagesschlusskurse; ATR14 = durchschnittliche Tagesspanne der letzten 14 Tage):\n"
            + "\n".join(lines))


def review_idea(idea: dict, frame: pd.DataFrame | None, since: date) -> dict:
    """Status of an earlier idea: Stop/Ziel erreicht (whichever came first) or offen, plus return since the report."""
    out = {**idea, "status": "keine Kursdaten", "return_pct": None, "last": None}
    if frame is None or frame.empty:
        return out
    before = frame[frame.index.date <= since]
    after = frame[frame.index.date > since]
    ref = float(before["Close"].iloc[-1]) if not before.empty else float(idea.get("entry") or 0)
    sign = 1 if idea.get("direction") == "long" else -1
    stop, target = float(idea["stop"]), float(idea["target"])
    status = "offen"
    for _, row in after.iterrows():
        hit_stop = row["Low"] <= stop if sign > 0 else row["High"] >= stop
        hit_target = row["High"] >= target if sign > 0 else row["Low"] <= target
        if hit_stop:  # same day: count conservatively as stop
            status = "Stop erreicht"
            break
        if hit_target:
            status = "Ziel erreicht"
            break
    last = float(frame["Close"].iloc[-1])
    out.update(status=status, last=last, return_pct=sign * _pct(last, ref) if ref else None)
    return out


def format_review(rows: list[dict], report_date: str) -> str:
    if not rows:
        return ""
    lines = [f"Rückblick: Trade-Ideen aus dem Report vom {report_date} (automatisch gegen Tageskurse geprüft):"]
    for r in rows:
        ret = "–" if r.get("return_pct") is None else f"{r['return_pct']:+.1f}%"
        lines.append(f"  - {r.get('name') or r.get('symbol')} [{r.get('symbol')}] {str(r.get('direction')).upper()}:"
                     f" Stop {_num(r.get('stop'))}, Ziel {_num(r.get('target'))}, aktuell {_num(r.get('last'))}"
                     f" -> {r['status']}, Performance seit Report {ret}")
    return "\n".join(lines)
