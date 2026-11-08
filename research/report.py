from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

import requests

logger = logging.getLogger(__name__)

# The model is chosen in the OpenRouter preset (openrouter.ai/settings/presets),
# currently anthropic/claude-haiku-5.5.
MODEL = "@preset/finanztools-research"
MAX_TOKENS = 16000
HISTORY_LIMIT = 10

API_URL = "https://openrouter.ai/api/v1/chat/completions"
REQUEST_TIMEOUT = 600
# Exa: $0.007 per search incl. 10 results; max_uses caps the searches per report.
WEB_SEARCH_TOOL = {
    "type": "openrouter:web_search",
    "parameters": {"engine": "exa", "max_results": 5, "max_uses": 10, "max_characters": 2000},
}

REPORT_PATH = "report.md"
JSON_PATH = "dashboard/data/research.json"
HISTORY_PATH = "dashboard/data/research_history.json"
DATA_DIR = "dashboard/data"
INSIDER_TOP = 12


def _read_json(path: str) -> Any:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("Market data %s not usable: %s", path, e)
        return None


def _fmt_usd(v: Any) -> str:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return "–"
    if n >= 1_000_000:
        return f"${n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"${n / 1_000:.0f}K"
    return f"${n:.0f}"


def _fg_section(d: dict) -> list[str]:
    lines = [
        f"Aktien Fear & Greed (CNN-Methodik, Stand {d.get('as_of')}): {d.get('score')} = {d.get('rating_de') or d.get('rating')}"
        f" | Vortag {d.get('previous_close')}, vor 1 Woche {d.get('one_week_ago')},"
        f" vor 1 Monat {d.get('one_month_ago')}, vor 1 Jahr {d.get('one_year_ago')}",
    ]
    for k in d.get("components") or []:
        if k.get("score") is not None:
            lines.append(f"  - {k.get('name_de') or k.get('name')}: Score {k.get('score')}"
                         f" ({k.get('rating_de') or k.get('rating')}), {k.get('value_label')}")
    return lines


def _futures_section(d: dict) -> list[str]:
    lines = [
        f"Bitcoin Futures Fear & Greed (Stand {d.get('as_of')}): 7-Tage-Mittel {d.get('index')} = {d.get('rating_de') or d.get('rating')}"
        f" | Tageswert {d.get('today')}, Vortag {d.get('previous_day')}, vor 1 Woche {d.get('one_week_ago')},"
        f" vor 1 Monat {d.get('one_month_ago')}",
    ]
    for g in d.get("groups") or []:
        for k in g.get("components") or []:
            if k.get("score") is not None:
                lines.append(f"  - {g.get('name_de')} / {k.get('name_de')}: Score {k.get('score')}, {k.get('value_label')}")
    return lines


def _cot_section(d: dict) -> list[str]:
    lines = [f"COT-Report (CFTC, Stand {d.get('report_date')}), Regel: Commercials Long auf 52W-Hoch + Kurs > SMA50 > SMA200:"]
    for s in d.get("buy_signals") or []:
        tr = s.get("trend") or {}
        lines.append(f"  - KAUFSIGNAL {s.get('commodity')} via {s.get('etf')} (2x ETF), halten bis {s.get('hold_until')},"
                     f" Kurs {tr.get('latest_close')}, SMA50 {tr.get('sma50')}, SMA200 {tr.get('sma200')}")
    for s in d.get("full_status") or []:
        lines.append(f"  - {s.get('commodity')}: Commercials-Signal {'ja' if s.get('commercial_signal') else 'nein'},"
                     f" Trend-Signal {'ja' if s.get('trend_signal') else 'nein'}")
    return lines


def _insider_section(d: dict) -> list[str]:
    trades = [t for t in d.get("trades") or [] if isinstance(t, dict)]
    clusters = sorted({t.get("ticker") for t in trades if t.get("cluster") and t.get("ticker")})
    lines = [f"Insider-Käufe (OpenInsider, letzte {d.get('window_days')} Tage, Stand {str(d.get('generated_at'))[:10]}):"
             f" {len(trades)} gefilterte Käufe, Cluster-Käufe bei: {', '.join(clusters) or 'keine'}"]
    top = sorted(trades, key=lambda t: float(t.get("value") or 0), reverse=True)[:INSIDER_TOP]
    for t in top:
        lines.append(f"  - {t.get('ticker')} ({t.get('company')}): {t.get('insider')} ({t.get('title')}) kaufte"
                     f" {_fmt_usd(t.get('value'))} am {t.get('trade_date')} zu ${t.get('price')},"
                     f" Bestandsänderung {t.get('delta_own')}%{' [CLUSTER]' if t.get('cluster') else ''}")
    return lines


def build_market_context(data_dir: str = DATA_DIR) -> str:
    """Compact text summary of the dashboard's own analyses; missing or broken files are skipped."""
    sections = [
        ("feargreed", _fg_section),
        ("futuresfg", _futures_section),
        ("cot", _cot_section),
        ("insider", _insider_section),
    ]
    parts = []
    for name, fn in sections:
        d = _read_json(os.path.join(data_dir, f"{name}.json"))
        if isinstance(d, dict):
            try:
                parts.append("\n".join(fn(d)))
            except Exception:
                logger.exception("Could not summarise %s.json", name)
    return "\n\n".join(parts)


def build_prompt(today: date, context: str = "") -> str:
    day = today.strftime("%d.%m.%Y")
    return f"""Heute ist der {day}. Du bist Marktanalyst und schreibst einen kompakten Markt-Research-Report auf Deutsch.

## Eigene Auswertungen aus dem Dashboard (Hauptgrundlage)
{context or "(Keine eigenen Auswertungen verfügbar.)"}

## Aufgabe
1. Werte die eigenen Auswertungen oben aus: Was sagen Fear & Greed (Aktien und Bitcoin-Futures), COT-Signale und Insider-Käufe zusammen über die Marktlage? Wo bestätigen oder widersprechen sie sich?
2. Durchsuche das Web nach News und Analysen der letzten 7 Tage zum allgemeinen Aktienmarkt (S&P 500, Nasdaq, DAX, Zinsen/Fed/EZB, Anleihen, Dollar, Rohstoffe) und zum Krypto-Markt (Bitcoin, Ethereum, ETF-Flows, Funding/Open Interest, Regulierung). Recherchiere auch kurz die Unternehmen mit den auffälligsten Insider-Käufen (Cluster oder große Beträge).
3. Leite daraus konkrete, begründete Trade-Ideen ab. Jede Idee muss sich auf mindestens eine der eigenen Auswertungen oder eine genannte Quelle stützen. Erfinde keine Kurse oder Zahlen; nenne nur Werte aus den Daten oben oder aus Quellen.

Gliedere den Report genau so:

# Research Report — {day}

## 🧭 Marktlage auf einen Blick
3-5 Bullet Points: Gesamtbild und Stimmung (Risk-on/Risk-off) mit Bezug auf die eigenen Indizes

## 📈 Aktienmarkt
Wichtigste Entwicklungen und Treiber der letzten 7 Tage, mit Quellen

## ₿ Krypto
Wichtigste Entwicklungen, Bezug auf den Bitcoin Futures Fear & Greed, mit Quellen

## 📡 COT & Insider
Was die COT-Signale und die auffälligsten Insider-Käufe bedeuten

## 💡 Trade-Ideen
3-5 Ideen als nummerierte Liste, je: **Instrument (Long/Short)** – Begründung mit Datenbezug; Auslöser/Einstieg; Invalidierung (wann die Idee falsch ist); Zeithorizont; Risiko (niedrig/mittel/hoch)

## ⚠️ Risiken & Termine
Wichtige Termine der nächsten 7 Tage (Notenbanken, Makrodaten, Earnings) und Hauptrisiken

---
*Automatisch erstellt, keine Anlageberatung.*

Regeln: max. ca. 1,5 Seiten, Fokus auf Signal statt Noise. Keine Markdown-Tabellen, nur Überschriften, Absätze und Listen.
Gib bei Web-Fakten die Quelle als Markdown-Link an.
Antworte nach der Recherche ausschließlich mit dem fertigen Markdown-Report, ohne Vorrede."""


def extract_report_text(content: str | None) -> str:
    """The report starts at its first heading; anything before it is search narration."""
    text = (content or "").strip()
    heading = text.find("# Research Report")
    return text[heading:].strip() if heading > 0 else text


def openrouter_sender(api_key: str) -> Callable[[dict], dict]:
    def send(payload: dict) -> dict:
        resp = requests.post(
            API_URL,
            json=payload,
            headers={"Authorization": f"Bearer {api_key}", "X-Title": "Finanztools Research"},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"OpenRouter HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    return send


def generate_report(
    send: Callable[[dict], dict], today: date | None = None, model: str = MODEL,
    context: str | None = None,
) -> tuple[str, str]:
    """Return the report and the model OpenRouter actually used."""
    prompt = build_prompt(today or date.today(), build_market_context() if context is None else context)
    data = send({
        "model": model,
        "max_tokens": MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
        "tools": [WEB_SEARCH_TOOL],
    })
    if data.get("error"):
        raise RuntimeError(f"OpenRouter error: {str(data['error'])[:300]}")
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"No choices in response: {str(data)[:300]}")

    choice = choices[0]
    usage = data.get("usage") or {}
    searches = (usage.get("server_tool_use") or {}).get("web_search_requests")
    used_model = data.get("model") or model
    logger.info(
        "model=%s, finish_reason=%s, searches=%s, tokens in/out=%s/%s, cost=%s",
        used_model, choice.get("finish_reason"), searches,
        usage.get("prompt_tokens"), usage.get("completion_tokens"), usage.get("cost"),
    )
    if choice.get("finish_reason") == "length":
        logger.warning("Report hit max_tokens and may be truncated")

    report = extract_report_text((choice.get("message") or {}).get("content"))
    if not report:
        raise RuntimeError(f"No report text in response (finish_reason={choice.get('finish_reason')})")
    return report, used_model


def build_entry(markdown: str, model: str = MODEL, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    return {
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date": now.date().isoformat(),
        "model": model,
        "markdown": markdown,
    }


def update_history(history: list[dict], entry: dict, limit: int = HISTORY_LIMIT) -> list[dict]:
    return [entry, *history][:limit]


def _load_history(path: str) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        logger.warning("Ignoring unreadable history file %s", path)
        return []
    return data if isinstance(data, list) else []


def _write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def write_outputs(
    entry: dict,
    report_path: str = REPORT_PATH,
    json_path: str = JSON_PATH,
    history_path: str = HISTORY_PATH,
) -> None:
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(entry["markdown"] + "\n")
    _write_json(json_path, entry)
    _write_json(history_path, update_history(_load_history(history_path), entry))
