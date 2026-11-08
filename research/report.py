from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

import requests

from insider.filters import insider_role

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
INSIDER_PRICE_TICKERS = 6
ROLE_DE = {"management": "Management", "director": "Board", "owner": "10%-Großaktionär", "other": "sonstiger Insider"}


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


def _rank(values: list[Any], current: Any) -> str:
    """Where the current value sits in its own stored history."""
    vals = [v for v in values if isinstance(v, (int, float))]
    if not vals or not isinstance(current, (int, float)):
        return ""
    lower = sum(v < current for v in vals)
    higher = sum(v > current for v in vals)
    if lower == 0:
        pos = "tiefster Wert der Historie"
    elif higher == 0:
        pos = "höchster Wert der Historie"
    else:
        pos = f"{lower / len(vals) * 100:.0f}%-Perzentil"
    return (f" | Historie ({len(vals)} Tage): {pos}, Min {min(vals)}, Max {max(vals)},"
            f" Tage mit Wert <= aktuell: {sum(v <= current for v in vals)}")


def _fg_section(d: dict) -> list[str]:
    hist = [h.get("score") for h in d.get("history") or [] if isinstance(h, dict)]
    lines = [
        f"Aktien Fear & Greed (CNN-Methodik, Stand {d.get('as_of')}): {d.get('score')} = {d.get('rating_de') or d.get('rating')}"
        f" | Vortag {d.get('previous_close')}, vor 1 Woche {d.get('one_week_ago')},"
        f" vor 1 Monat {d.get('one_month_ago')}, vor 1 Jahr {d.get('one_year_ago')}" + _rank(hist, d.get("score")),
    ]
    for k in d.get("components") or []:
        if k.get("score") is not None:
            lines.append(f"  - {k.get('name_de') or k.get('name')}: Score {k.get('score')}"
                         f" ({k.get('rating_de') or k.get('rating')}), {k.get('value_label')}")
    return lines


def _futures_section(d: dict) -> list[str]:
    hist = [h.get("index") for h in d.get("history") or [] if isinstance(h, dict)]
    lines = [
        f"Bitcoin Futures Fear & Greed (Stand {d.get('as_of')}): 7-Tage-Mittel {d.get('index')} = {d.get('rating_de') or d.get('rating')}"
        f" | Tageswert {d.get('today')}, Vortag {d.get('previous_day')}, vor 1 Woche {d.get('one_week_ago')},"
        f" vor 1 Monat {d.get('one_month_ago')}" + _rank(hist, d.get("index")),
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


def _role(t: dict) -> str:
    return t.get("role") or insider_role(t.get("title") or "")


def _aggregate_insiders(trades: list[dict]) -> list[dict]:
    """One row per ticker + insider: repeated buys (often a 10b5-1 plan) become one line."""
    groups: dict[tuple, dict] = {}
    for t in trades:
        key = (t.get("ticker"), (t.get("insider") or "").strip().lower())
        g = groups.setdefault(key, {**t, "value": 0.0, "n": 0, "dates": [], "prices": []})
        g["value"] += float(t.get("value") or 0)
        g["n"] += 1
        g["dates"].append(str(t.get("trade_date")))
        if t.get("price") is not None:
            g["prices"].append(float(t["price"]))
        g["cluster"] = bool(g.get("cluster") or t.get("cluster"))
        if isinstance(t.get("delta_own"), (int, float)):
            g["delta_own"] = max(t["delta_own"], g["delta_own"] if isinstance(g.get("delta_own"), (int, float)) else 0)
    return sorted(groups.values(), key=lambda g: g["value"], reverse=True)


def _delta(v: Any) -> str:
    return f"+{v:.0f}%" if isinstance(v, (int, float)) else "neue Position/unbekannt"


def _insider_section(d: dict) -> list[str]:
    trades = [t for t in d.get("trades") or [] if isinstance(t, dict)]
    clusters = sorted({t.get("ticker") for t in trades if t.get("cluster") and t.get("ticker")})
    roles = [_role(t) for t in trades]
    lines = [
        f"Insider-Käufe (OpenInsider, letzte {d.get('window_days')} Tage, Stand {str(d.get('generated_at'))[:10]}):"
        f" {len(trades)} gefilterte Käufe ({roles.count('management')} Management, {roles.count('director')} Board,"
        f" {roles.count('owner')} reine 10%-Großaktionäre), Cluster-Käufe bei: {', '.join(clusters) or 'keine'}",
        "  Hinweis: Käufe von Management/Board sind das stärkste Signal. Reine 10%-Großaktionäre (Fonds, Versicherer)"
        " und viele gleichartige Käufe ohne Bestandsänderung (oft Handelsplan nach Rule 10b5-1) sind schwächer."
        " Bei mehreren Transaktionen in einer Meldung zeigt OpenInsider einen Durchschnittspreis.",
    ]
    for g in _aggregate_insiders(trades)[:INSIDER_TOP]:
        prices = g["prices"]
        if len(set(prices)) > 1:
            price = f"${min(prices):.2f}–${max(prices):.2f}"
        else:
            price = f"${prices[0]:.2f}" if prices else "–"
        dates = sorted(set(g["dates"]))
        when = dates[0] if len(dates) == 1 else f"{dates[0]} bis {dates[-1]}"
        many = f" in {g['n']} Käufen" if g["n"] > 1 else ""
        lines.append(f"  - {g.get('ticker')} ({g.get('company')}): {g.get('insider')} ({g.get('title')};"
                     f" {ROLE_DE.get(_role(g), _role(g))}) kaufte {_fmt_usd(g['value'])}{many} am {when} zu {price},"
                     f" Bestandsänderung {_delta(g.get('delta_own'))}{' [CLUSTER]' if g.get('cluster') else ''}")
    return lines


def insider_symbols(data_dir: str = DATA_DIR, limit: int = INSIDER_PRICE_TICKERS) -> dict[str, str]:
    """Label -> ticker of the largest insider buys, management/board before 10% holders, for price lookups."""
    d = _read_json(os.path.join(data_dir, "insider.json"))
    trades = [t for t in (d or {}).get("trades") or [] if isinstance(t, dict) and t.get("ticker")]
    ranked = sorted(_aggregate_insiders(trades), key=lambda g: (_role(g) == "owner", -g["value"]))
    out: dict[str, str] = {}
    for g in ranked:
        if len(out) >= limit:
            break
        if "acquisition" in str(g.get("company")).lower():  # SPAC units: no meaningful chart
            continue
        if g["ticker"] not in out.values():
            out[f"{g.get('company') or g['ticker']} (Insider-Kauf)"] = g["ticker"]
    return out


def build_market_context(data_dir: str = DATA_DIR, extra: list[str] | tuple[str, ...] = ()) -> str:
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
    parts.extend(e for e in extra if e)
    return "\n\n".join(parts)


def assemble_context(
    data_dir: str = DATA_DIR,
    history: list[dict] | None = None,
    fetch: Callable[[list[str]], dict] | None = None,
) -> str:
    """Dashboard data + price levels + review of the previous report's ideas. Price errors only drop that part."""
    from research import prices

    fetch = fetch or prices.fetch_history
    prev = (history or [None])[0] or {}
    prev_ideas = [i for i in prev.get("ideas") or [] if isinstance(i, dict) and i.get("symbol")]
    extra_syms = insider_symbols(data_dir)
    symbols = [*prices.MARKETS.values(), *extra_syms.values(), *(i["symbol"] for i in prev_ideas)]
    try:
        hist = fetch(symbols)
    except Exception:
        logger.exception("Price download failed, report runs without price data")
        hist = {}
    sections = [prices.format_markets(hist, extra_syms)]
    if prev_ideas and prev.get("date"):
        try:
            since = date.fromisoformat(prev["date"])
            rows = [prices.review_idea(i, hist.get(i["symbol"]), since) for i in prev_ideas]
            sections.append(prices.format_review(rows, prev["date"]))
        except Exception:
            logger.exception("Could not review previous ideas")
    return build_market_context(data_dir, sections)


def build_prompt(today: date, context: str = "") -> str:
    day = today.strftime("%d.%m.%Y")
    return f"""Heute ist der {day}. Du bist Marktanalyst und schreibst einen kompakten Markt-Research-Report auf Deutsch.

## Eigene Auswertungen aus dem Dashboard (Hauptgrundlage)
{context or "(Keine eigenen Auswertungen verfügbar.)"}

## Aufgabe
1. Werte die eigenen Auswertungen oben aus: Was sagen Fear & Greed (Aktien und Bitcoin-Futures), COT-Signale und Insider-Käufe zusammen über die Marktlage? Wo bestätigen oder widersprechen sie sich?
2. Durchsuche das Web nach News und Analysen der letzten 7 Tage zum allgemeinen Aktienmarkt (S&P 500, Nasdaq, DAX, Zinsen/Fed/EZB, Anleihen, Dollar, Rohstoffe) und zum Krypto-Markt (Bitcoin, Ethereum, ETF-Flows, Funding/Open Interest, Regulierung). Recherchiere auch kurz die Unternehmen mit den auffälligsten Insider-Käufen (Cluster oder große Beträge).
3. Leite daraus konkrete, begründete Trade-Ideen ab. Jede Idee muss sich auf mindestens eine der eigenen Auswertungen oder eine genannte Quelle stützen. Erfinde keine Kurse oder Zahlen; nenne nur Werte aus den Daten oben oder aus Quellen.

## Regeln für Trade-Ideen (Pflicht)
- Kursniveaus (Einstieg, Stop, Ziel) nur aus den Kursdaten oben ableiten (Schlusskurs, SMA, 52W-Spanne, ATR14). Hat ein Instrument keine Kursdaten oben, keine Kursniveaus nennen und es nicht als Idee aufnehmen.
- Stop mindestens 1× ATR14 vom Einstieg entfernt und außerhalb der Einstiegszone. Long: Stop < Einstieg < Ziel. Short: Ziel < Einstieg < Stop.
- Chance-Risiko-Verhältnis (CRV = Abstand Ziel / Abstand Stop) mindestens 2; das CRV bei jeder Idee angeben.
- Extremwerte immer auch konträr prüfen: Extreme Angst ist historisch oft eher Kaufgelegenheit als Verkaufssignal, extreme Gier umgekehrt. Nutze den Historien-Rang oben. Wenn du trotzdem gegen das konträre Signal handelst, begründe es.
- Insider: Käufe von Management/Board höher gewichten als die von reinen 10%-Großaktionären oder Plan-Käufe.
- COT: Ein Commercials-Signal ohne Trend-Bestätigung ist ein Frühwarnsignal, kein Kaufsignal; als Beobachtung nennen.
- Höchstens eine Idee pro Anlageklasse (Aktienindex, Einzelaktie, Anleihen, Rohstoffe, Krypto), maximal 4 Ideen. Je Idee eine Überzeugung (niedrig/mittel/hoch).
- Gibt es keine Idee, die diese Regeln erfüllt, schreibe ehrlich „Diese Woche keine Idee mit ausreichendem CRV“ statt eine schwache Idee zu erzwingen.

Gliedere den Report genau so:

# Research Report — {day}

## 🔁 Rückblick Vorwoche
Nur wenn oben ein Rückblick steht: Status jeder früheren Idee (Stop/Ziel erreicht/offen, Performance) und eine kurze Lehre daraus. Sonst diesen Abschnitt weglassen.

## 🧭 Marktlage auf einen Blick
3-5 Bullet Points: Gesamtbild und Stimmung (Risk-on/Risk-off) mit Bezug auf die eigenen Indizes

## 📈 Aktienmarkt
Wichtigste Entwicklungen und Treiber der letzten 7 Tage, mit Quellen

## ₿ Krypto
Wichtigste Entwicklungen, Bezug auf den Bitcoin Futures Fear & Greed, mit Quellen

## 📡 COT & Insider
Was die COT-Signale und die auffälligsten Insider-Käufe bedeuten

## 💡 Trade-Ideen
0-4 Ideen als nummerierte Liste, je: **Instrument (Long/Short)** – Begründung mit Datenbezug (auch konträre Einordnung); Einstieg; Stop (Invalidierung, Abstand in ATR); Ziel; CRV; Zeithorizont; Überzeugung (niedrig/mittel/hoch)

## ⚠️ Risiken & Termine
Wichtige Termine der nächsten 7 Tage (Notenbanken, Makrodaten, Earnings) und Hauptrisiken

---
*Automatisch erstellt, keine Anlageberatung.*

Hänge ganz am Ende einen JSON-Block mit genau den Trade-Ideen aus dem Abschnitt oben an (leere Liste, wenn es keine gibt). Er wird maschinell ausgewertet und nicht angezeigt:
```json
{{"ideas": [{{"name": "Gold", "symbol": "GC=F", "direction": "long", "entry": 4065.0, "stop": 3950.0, "target": 4300.0, "horizon_weeks": 4, "conviction": "mittel"}}]}}
```
`symbol` ist das Yahoo-Finance-Symbol aus den eckigen Klammern der Kursdaten oben, `direction` ist "long" oder "short", Kurse als Zahlen.

Regeln: max. ca. 1,5 Seiten, Fokus auf Signal statt Noise. Keine Markdown-Tabellen, nur Überschriften, Absätze und Listen.
Gib bei Web-Fakten die Quelle als Markdown-Link an.
Antworte nach der Recherche ausschließlich mit dem fertigen Markdown-Report und dem JSON-Block, ohne Vorrede."""


def extract_report_text(content: str | None) -> str:
    """The report starts at its first heading; anything before it is search narration."""
    text = (content or "").strip()
    heading = text.find("# Research Report")
    return text[heading:].strip() if heading > 0 else text


_IDEAS_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


def _valid_idea(i: Any) -> dict | None:
    if not isinstance(i, dict) or not i.get("symbol") or i.get("direction") not in ("long", "short"):
        return None
    try:
        entry, stop, target = float(i["entry"]), float(i["stop"]), float(i["target"])
    except (KeyError, TypeError, ValueError):
        return None
    ordered = stop < entry < target if i["direction"] == "long" else target < entry < stop
    if not ordered:
        logger.warning("Dropping idea with inconsistent levels: %s", i)
        return None
    return {
        "name": str(i.get("name") or i["symbol"]),
        "symbol": str(i["symbol"]),
        "direction": i["direction"],
        "entry": entry,
        "stop": stop,
        "target": target,
        "rr": round(abs(target - entry) / abs(entry - stop), 2),
        "horizon_weeks": i.get("horizon_weeks"),
        "conviction": i.get("conviction"),
    }


def split_ideas(report: str) -> tuple[str, list[dict]]:
    """Remove the trailing machine-readable ideas block from the report and return the valid ideas."""
    matches = list(_IDEAS_BLOCK.finditer(report or ""))
    if not matches:
        logger.warning("Report has no ideas JSON block")
        return (report or "").strip(), []
    m = matches[-1]
    text = (report[:m.start()] + report[m.end():]).strip()
    try:
        raw = json.loads(m.group(1)).get("ideas") or []
    except (json.JSONDecodeError, AttributeError):
        logger.warning("Ideas JSON block is not valid JSON")
        return text, []
    ideas = [v for v in (_valid_idea(i) for i in raw) if v]
    return text, ideas


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


def build_entry(
    markdown: str, model: str = MODEL, now: datetime | None = None, ideas: list[dict] | None = None
) -> dict:
    now = now or datetime.now(UTC)
    return {
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date": now.date().isoformat(),
        "model": model,
        "markdown": markdown,
        "ideas": ideas or [],
    }


def update_history(history: list[dict], entry: dict, limit: int = HISTORY_LIMIT) -> list[dict]:
    return [entry, *history][:limit]


def load_history(path: str = HISTORY_PATH) -> list[dict]:
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
    _write_json(history_path, update_history(load_history(history_path), entry))
