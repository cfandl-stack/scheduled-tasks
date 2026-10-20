import json
from datetime import date

from futuresfg import store


def test_merge_fresh_wins_and_skips_incomplete_days():
    s = {"funding": {"2026-10-17": 1.0, "2026-10-18": 2.0}}
    out = store.merge(s, "funding", {"2026-10-18": 5.0, "2026-10-19": 6.0, "2026-10-20": 7.0},
                      before=date(2026, 10, 20))
    assert out["funding"] == {"2026-10-17": 1.0, "2026-10-18": 5.0, "2026-10-19": 6.0}
    assert s["funding"]["2026-10-18"] == 2.0  # input not mutated


def test_merge_drops_non_finite_values():
    out = store.merge({}, "x", {"2026-01-01": float("nan"), "2026-01-02": {"long": 1.0, "short": float("inf")},
                                "2026-01-03": 3}, before=date(2026, 10, 20))
    assert out["x"] == {"2026-01-03": 3}


def test_merge_empty_fetch_keeps_history():
    s = {"vix": {"2026-10-17": 16.9}}
    assert store.merge(s, "vix", {}, before=date(2026, 10, 20)) == s


def test_prune_older_than_800_days():
    s = {"a": {"2024-08-10": 1.0, "2024-08-11": 2.0, "2026-10-19": 3.0}}
    out = store.prune(s, date(2026, 10, 20))
    assert out["a"] == {"2024-08-11": 2.0, "2026-10-19": 3.0}


def test_roundtrip_and_corrupt_file(tmp_path):
    path = tmp_path / "sub" / "raw.json"
    data = {"b": {"2026-01-01": {"long": 1.5e8, "short": 2.0}}, "a": {"2026-01-02": 0.0049}}
    store.save(data, str(path))
    assert store.load(str(path)) == data
    assert json.loads(path.read_text()) == data
    path.write_text("{not json")
    assert store.load(str(path)) == {}
    assert store.load(str(tmp_path / "missing.json")) == {}


def test_last_date_and_count():
    s = {"a": {"2026-01-01": 1, "2026-02-01": 2}}
    assert store.last_date(s, "a") == date(2026, 2, 1)
    assert store.last_date(s, "b") is None
    assert store.count_since(s, "a", date(2026, 1, 15)) == 1
