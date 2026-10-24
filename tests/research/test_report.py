import json
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from research import report
from research.report import (
    build_entry,
    extract_report_text,
    generate_report,
    openrouter_sender,
    update_history,
    write_outputs,
)


class FakeSender:
    def __init__(self, responses: list[dict]):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def __call__(self, payload: dict) -> dict:
        self.calls.append(payload)
        return self._responses.pop(0)


def _resp(content, finish_reason: str = "stop", searches: int = 3) -> dict:
    # Shape of an OpenRouter /chat/completions response with the web search server tool.
    return {
        "id": "gen-1",
        "model": report.MODEL,
        "choices": [{
            "index": 0,
            "finish_reason": finish_reason,
            "message": {"role": "assistant", "content": content, "annotations": [
                {"type": "url_citation", "url_citation": {"url": "https://example.com", "title": "x"}},
            ]},
        }],
        "usage": {"prompt_tokens": 30000, "completion_tokens": 2000, "cost": 0.03,
                  "server_tool_use": {"web_search_requests": searches}},
    }


class TestGenerateReport:
    def test_returns_report(self):
        send = FakeSender([_resp("# Research Report — 20.10.2026\n\nInhalt")])
        assert generate_report(send, date(2026, 10, 20)) == "# Research Report — 20.10.2026\n\nInhalt"
        assert len(send.calls) == 1

    def test_request_uses_web_search_tool_and_model(self):
        send = FakeSender([_resp("# Report")])
        generate_report(send, date(2026, 10, 20))
        call = send.calls[0]
        assert call["model"] == report.MODEL
        tool = call["tools"][0]
        assert tool["type"] == "openrouter:web_search"
        assert tool["parameters"]["max_uses"] > 0
        assert "20.10.2026" in call["messages"][0]["content"]
        assert "48 Stunden" in call["messages"][0]["content"]

    def test_empty_content_raises(self):
        with pytest.raises(RuntimeError, match="No report text"):
            generate_report(FakeSender([_resp(None)]))

    def test_error_object_raises(self):
        send = FakeSender([{"error": {"code": 402, "message": "Insufficient credits"}}])
        with pytest.raises(RuntimeError, match="Insufficient credits"):
            generate_report(send)

    def test_no_choices_raises(self):
        with pytest.raises(RuntimeError, match="No choices"):
            generate_report(FakeSender([{"choices": []}]))

    def test_truncated_report_is_kept(self):
        send = FakeSender([_resp("# Research Report — x\nTeil", finish_reason="length")])
        assert generate_report(send) == "# Research Report — x\nTeil"


class TestOpenRouterSender:
    def test_posts_with_bearer_key(self, monkeypatch):
        seen = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            seen.update(url=url, json=json, headers=headers)
            return SimpleNamespace(status_code=200, json=lambda: {"ok": True}, text="")

        monkeypatch.setattr(report.requests, "post", fake_post)
        assert openrouter_sender("sk-or-test")({"model": "m"}) == {"ok": True}
        assert seen["url"] == report.API_URL
        assert seen["headers"]["Authorization"] == "Bearer sk-or-test"
        assert seen["json"] == {"model": "m"}

    def test_http_error_raises(self, monkeypatch):
        monkeypatch.setattr(report.requests, "post", lambda *a, **k: SimpleNamespace(
            status_code=401, text='{"error":{"message":"No auth credentials found"}}'))
        with pytest.raises(RuntimeError, match="HTTP 401"):
            openrouter_sender("bad")({})


class TestExtractReportText:
    def test_drops_narration_before_heading(self):
        assert extract_report_text("Ich suche zuerst.\n\n# Research Report — x\nA") == "# Research Report — x\nA"

    def test_keeps_text_without_heading(self):
        assert extract_report_text(" # Anderer Titel ") == "# Anderer Titel"

    def test_empty(self):
        assert extract_report_text(None) == ""
        assert extract_report_text("") == ""


class TestHistory:
    def test_newest_first(self):
        assert update_history([{"n": 1}], {"n": 2}) == [{"n": 2}, {"n": 1}]

    def test_trimmed_to_ten(self):
        history = [{"n": i} for i in range(10)]
        result = update_history(history, {"n": "new"})
        assert len(result) == 10
        assert result[0] == {"n": "new"}
        assert result[-1] == {"n": 8}


class TestOutputs:
    def test_build_entry_format(self):
        entry = build_entry("# R", model="m", now=datetime(2026, 10, 20, 6, 17, 5, tzinfo=UTC))
        assert entry == {
            "generated_at": "2026-10-20T06:17:05Z",
            "date": "2026-10-20",
            "model": "m",
            "markdown": "# R",
        }

    def test_write_outputs(self, tmp_path):
        report_path = tmp_path / "report.md"
        json_path = tmp_path / "data" / "research.json"
        history_path = tmp_path / "data" / "research_history.json"
        paths = dict(report_path=str(report_path), json_path=str(json_path), history_path=str(history_path))

        for i in range(12):
            write_outputs(build_entry(f"# R{i} äöü", model="m"), **paths)

        assert report_path.read_text(encoding="utf-8") == "# R11 äöü\n"
        latest = json.loads(json_path.read_text(encoding="utf-8"))
        assert latest["markdown"] == "# R11 äöü"
        history = json.loads(history_path.read_text(encoding="utf-8"))
        assert len(history) == 10
        assert [h["markdown"] for h in history[:2]] == ["# R11 äöü", "# R10 äöü"]
        assert history[0] == latest

    def test_corrupt_history_is_replaced(self, tmp_path):
        history_path = tmp_path / "h.json"
        history_path.write_text("{not json")
        write_outputs(
            build_entry("# R"),
            report_path=str(tmp_path / "r.md"),
            json_path=str(tmp_path / "j.json"),
            history_path=str(history_path),
        )
        assert len(json.loads(history_path.read_text())) == 1
