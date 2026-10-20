from __future__ import annotations

import json
import logging
import os
from datetime import UTC, date, datetime
from typing import Any

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-5-5"
MAX_TOKENS = 16000
MAX_CONTINUATIONS = 5
HISTORY_LIMIT = 10

WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": 15}
FALLBACK_BETA = "server-side-fallback-2026-07-01"

REPORT_PATH = "report.md"
JSON_PATH = "dashboard/data/research.json"
HISTORY_PATH = "dashboard/data/research_history.json"

_TOOL_BLOCK_TYPES = {"server_tool_use", "web_search_tool_result"}


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


def _block_type(block: Any) -> str | None:
    return block.get("type") if isinstance(block, dict) else getattr(block, "type", None)


def _block_text(block: Any) -> str:
    return block.get("text", "") if isinstance(block, dict) else getattr(block, "text", "")


def extract_report_text(content: list[Any]) -> str:
    """Join the text blocks that follow the last web search; earlier text is search narration."""
    last_tool = -1
    for i, block in enumerate(content):
        if _block_type(block) in _TOOL_BLOCK_TYPES:
            last_tool = i
    texts = [_block_text(b) for b in content[last_tool + 1:] if _block_type(b) == "text"]
    if not "".join(texts).strip():
        texts = [_block_text(b) for b in content if _block_type(b) == "text"]
    return "".join(texts).strip()


def generate_report(client: Any, today: date | None = None, model: str = MODEL) -> str:
    prompt = build_prompt(today or date.today())
    messages: list[dict] = [{"role": "user", "content": prompt}]
    turn_content: list[Any] = []

    for attempt in range(MAX_CONTINUATIONS + 1):
        response = client.beta.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            tools=[WEB_SEARCH_TOOL],
            messages=messages,
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        turn_content.extend(response.content)
        logger.info("API call %d: stop_reason=%s", attempt + 1, response.stop_reason)

        if response.stop_reason != "pause_turn":
            break
        # Server-side search loop paused: resend the partial assistant turn so it resumes.
        messages = [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": list(turn_content)},
        ]
    else:
        raise RuntimeError(f"Turn still paused after {MAX_CONTINUATIONS} continuations")

    if response.stop_reason == "refusal":
        raise RuntimeError("Model refused the request")
    if response.stop_reason == "max_tokens":
        logger.warning("Report hit max_tokens and may be truncated")

    report = extract_report_text(turn_content)
    if not report:
        raise RuntimeError(f"No report text in response (stop_reason={response.stop_reason})")
    return report


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
