from ledger import COLUMNS, append_row, read_rows, scored_keys


def _row(commit="a" * 40, tier="t0", **kw):
    base = {c: "" for c in COLUMNS}
    base.update(commit=commit, branch="exp/001", tier=tier, status="ok")
    base.update(kw)
    return base


def test_append_and_read_roundtrip(tmp_path):
    path = tmp_path / "ledger.tsv"
    append_row(path, _row(score_bytes="123"))
    append_row(path, _row(tier="t1", score_bytes="456"))
    rows = read_rows(path)
    assert len(rows) == 2
    assert rows[0]["score_bytes"] == "123"
    assert rows[1]["tier"] == "t1"


def test_header_written_once(tmp_path):
    path = tmp_path / "ledger.tsv"
    append_row(path, _row())
    append_row(path, _row(tier="t1"))
    assert path.read_text().count("commit\t") == 1


def test_scored_keys(tmp_path):
    path = tmp_path / "ledger.tsv"
    append_row(path, _row(commit="a" * 40, tier="t0"))
    append_row(path, _row(commit="a" * 40, tier="t1"))
    keys = scored_keys(read_rows(path))
    assert ("a" * 40, "t0") in keys
    assert ("a" * 40, "t1") in keys
    assert ("b" * 40, "t0") not in keys


def test_read_missing_file(tmp_path):
    assert read_rows(tmp_path / "nope.tsv") == []
