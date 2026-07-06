from runner import Job, parse_tier, select_jobs


def test_parse_tier_valid():
    assert parse_tier("t1") == "t1"
    assert parse_tier("  t2\n") == "t2"


def test_parse_tier_defaults_to_t0():
    assert parse_tier("") == "t0"
    assert parse_tier("bogus") == "t0"


def test_select_jobs_filters_scored_and_sorts_fifo():
    heads = [
        Job(branch="exp/002", commit="b" * 40, tier="t0", committed_at=200),
        Job(branch="exp/001", commit="a" * 40, tier="t1", committed_at=100),
        Job(branch="exp/003", commit="c" * 40, tier="t0", committed_at=300),
    ]
    scored = {("b" * 40, "t0")}
    jobs = select_jobs(heads, scored)
    assert [j.branch for j in jobs] == ["exp/001", "exp/003"]


def test_select_jobs_rescores_same_commit_at_new_tier():
    heads = [Job(branch="exp/001", commit="a" * 40, tier="t1", committed_at=100)]
    scored = {("a" * 40, "t0")}
    assert len(select_jobs(heads, scored)) == 1
