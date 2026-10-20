import json
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from research import report
from research.report import (
    build_entry,
    extract_report_text,
    generate_report,
    update_history,
    write_outputs,
)


def _text(t: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=t)


def _search() -> SimpleNamespace:
    return SimpleNamespace(type="server_tool_use", id="srvtoolu_1", name="web_search")


def _result() -> SimpleNamespace:
    return SimpleNamespace(type="web_search_tool_result", tool_use_id="srvtoolu_1", content=[])


class FakeClient:
    def __init__(self, responses: list[SimpleNamespace]):
        self._responses = list(responses)
        self.calls: list[dict] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


def _resp(stop_reason: str, *content) -> SimpleNamespace:
    return SimpleNamespace(stop_reason=stop_reason, content=list(content))


class TestGenerateReport:
    def test_single_call_end_turn(self):
        client = FakeClient([_resp("end_turn", _text("Suche..."), _search(), _result(), _text("# Report"))])
        assert generate_report(client, date(2026, 10, 20)) == "# Report"
        assert len(client.calls) == 1

    def test_request_uses_web_search_tool_and_model(self):
        client = FakeClient([_resp("end_turn", _text("# Report"))])
        generate_report(client, date(2026, 10, 20))
        call = client.calls[0]
        assert call["model"] == report.MODEL
        tool = call["tools"][0]
        assert tool["name"] == "web_search"
        assert tool["type"].startswith("web_search_")
        assert "20.10.2026" in call["messages"][0]["content"]
        assert "48 Stunden" in call["messages"][0]["content"]

    def test_pause_turn_resends_assistant_content(self):
        first = [_text("Ich suche."), _search(), _result()]
        client = FakeClient([
            _resp("pause_turn", *first),
            _resp("end_turn", _search(), _result(), _text("# Fertig")),
        ])
        assert generate_report(client) == "# Fertig"
        assert len(client.calls) == 2
        msgs = client.calls[1]["messages"]
        assert [m["role"] for m in msgs] == ["user", "assistant"]
        assert msgs[1]["content"] == first
        assert not any(
            isinstance(b, dict) and b.get("type") == "tool_result"
            for m in msgs for b in (m["content"] if isinstance(m["content"], list) else [])
        )

    def test_text_before_pause_is_kept_when_final_has_no_search(self):
        client = FakeClient([
            _resp("pause_turn", _search(), _result(), _text("# Teil 1\n")),
            _resp("end_turn", _text("Teil 2")),
        ])
        assert generate_report(client) == "# Teil 1\nTeil 2"

    def test_pause_turn_is_bounded(self):
        responses = [_resp("pause_turn", _search(), _result())] * (report.MAX_CONTINUATIONS + 1)
        client = FakeClient(responses)
        with pytest.raises(RuntimeError, match="paused"):
            generate_report(client)
        assert len(client.calls) == report.MAX_CONTINUATIONS + 1

    def test_no_text_raises(self):
        client = FakeClient([_resp("end_turn", _search(), _result())])
        with pytest.raises(RuntimeError, match="No report text"):
            generate_report(client)

    def test_refusal_raises(self):
        client = FakeClient([_resp("refusal")])
        with pytest.raises(RuntimeError, match="refused"):
            generate_report(client)


class TestExtractReportText:
    def test_drops_narration_before_last_search(self):
        content = [_text("Ich suche zuerst."), _search(), _result(), _text("# A"), _text("\nB")]
        assert extract_report_text(content) == "# A\nB"

    def test_falls_back_to_all_text(self):
        content = [_text("# Nur Text"), _search(), _result()]
        assert extract_report_text(content) == "# Nur Text"

    def test_accepts_dict_blocks(self):
        assert extract_report_text([{"type": "text", "text": " x "}]) == "x"

    def test_empty(self):
        assert extract_report_text([]) == ""


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
