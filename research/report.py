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


def build_prompt(today: date) -> str:
    day = today.strftime("%d.%m.%Y")
    return f"""Heute ist der {day}. Durchsuche das Web nach aktuellen Posts und News der letzten 48 Stunden zu folgenden Themen:

1. Suche auf Reddit (r/algotrading, r/ClaudeAI, r/ChatGPTCoding, r/openclaw) und im Web nach:
   - Trading Bots und algorithmischer Handel mit AI/LLMs
   - OpenClaw — Use Cases, Projekte und Erfahrungen
   - OpenClaw speziell für Trading oder Finance-Automatisierung

2. Finde die interessantesten und meistdiskutierten Beiträge/Diskussionen.

3. Erstelle einen strukturierten Report auf Deutsch mit diesen Abschnitten:

# Research Report — {day}

## 🤖 Trading & Finance Bots
Top Highlights und Diskussionen der letzten 48h

## 🦀 OpenClaw Use Cases
Interessante Projekte, die Leute bauen

## 🦀📈 OpenClaw + Trading
Spezifische Finance/Trading-Anwendungen

## 💡 Key Takeaways
3-5 Bullet Points, die man wissen sollte

---
Halte den Report kompakt (max 1 Seite). Fokus auf Signal, nicht Noise.
Gib bei jedem Punkt die Quelle/den Link an, wenn verfügbar.
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
    send: Callable[[dict], dict], today: date | None = None, model: str = MODEL
) -> tuple[str, str]:
    """Return the report and the model OpenRouter actually used."""
    prompt = build_prompt(today or date.today())
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
