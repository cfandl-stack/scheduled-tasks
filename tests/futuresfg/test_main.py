import json
import re

from futuresfg import main as ffg_main
from futuresfg import store
from futuresfg.components import COMPONENTS, Source
from tests.futuresfg.conftest import TODAY, fake_components


def _boom(start):
    raise ConnectionError("HTTP 451")


def test_main_writes_output_and_raw_store(tmp_path):
    out, raw = tmp_path / "data" / "futuresfg.json", tmp_path / "data" / "futuresfg_raw.json"
    assert ffg_main.main(str(out), str(raw), fake_components(), TODAY) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", data["generated_at"])
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", data["as_of"])
    for key in ("index", "today"):
        assert isinstance(data[key], int) and 0 <= data[key] <= 100
    for key in ("previous_day", "one_week_ago", "one_month_ago"):
        assert data[key] is None or isinstance(data[key], int)
    assert data["rating"] in {"Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"}
    assert all(set(h) == {"date", "daily", "index"} for h in data["history"])
    raw_data = store.load(str(raw))
    assert set(raw_data) == {c.key for c in COMPONENTS}
    assert max(raw_data["funding"]) == "2026-10-19"


def test_failure_does_not_overwrite(tmp_path):
    out, raw = tmp_path / "futuresfg.json", tmp_path / "futuresfg_raw.json"
    out.write_text('{"old": true}')
    raw.write_text('{"vix": {"2026-10-01": 16.9}}')
    comps = fake_components(overrides={c.key: (Source("X", _boom),) for c in COMPONENTS})
    assert ffg_main.main(str(out), str(raw), comps, TODAY) == 1
    assert out.read_text() == '{"old": true}'
    assert raw.read_text() == '{"vix": {"2026-10-01": 16.9}}'
    assert not (tmp_path / "futuresfg.json.tmp").exists()


def test_raw_store_accumulates_across_runs(tmp_path):
    out, raw = tmp_path / "f.json", tmp_path / "r.json"
    assert ffg_main.main(str(out), str(raw), fake_components(), TODAY) == 0
    first = store.load(str(raw))
    only_today = {"2026-10-19": 0.5}
    comps = fake_components(overrides={"funding": (Source("Hyperliquid", lambda s: only_today),)})
    assert ffg_main.main(str(out), str(raw), comps, TODAY) == 0
    second = store.load(str(raw))
    assert len(second["funding"]) == len(first["funding"])
    assert second["funding"]["2026-10-19"] == 0.5
    data = json.loads(out.read_text())
    funding = data["groups"][0]["components"][0]
    assert funding["source"] == "Hyperliquid" and funding["value_label"] == "+0,5000 %"
