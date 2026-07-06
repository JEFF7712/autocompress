from report import baselines, deltas


def _row(branch, tier, score, status="ok", commit="c" * 40):
    return {
        "commit": commit,
        "branch": branch,
        "tier": tier,
        "status": status,
        "score_bytes": str(score),
        "cpu_seconds_comp": "100.0",
        "description": "test row",
    }


ROWS = [
    _row("main", "t0", 1_000_000),
    _row("main", "t1", 10_000_000),
    _row("exp/001", "t0", 990_000),
    _row("exp/001", "t1", 9_950_000),
    _row("exp/002", "t0", 1_010_000),
    _row("exp/003", "t0", 0, status="crash"),
]


def test_baselines_latest_ok_main_row_per_tier():
    b = baselines(ROWS)
    assert b["t0"]["score_bytes"] == "1000000"
    assert b["t1"]["score_bytes"] == "10000000"


def test_deltas_vs_baseline():
    d = deltas(ROWS)
    exp1_t0 = next(r for r in d if r["branch"] == "exp/001" and r["tier"] == "t0")
    assert exp1_t0["delta_bytes"] == -10_000
    exp2 = next(r for r in d if r["branch"] == "exp/002")
    assert exp2["delta_bytes"] == 10_000


def test_deltas_skips_failed_rows():
    d = deltas(ROWS)
    assert not any(r["branch"] == "exp/003" for r in d)
