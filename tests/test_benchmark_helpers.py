from benchmark import classify_failure, render_output


def test_classify_ok():
    assert (
        classify_failure(
            0, cpu_seconds=10, cpu_limit=100, peak_rss=1_000, ram_limit=10_000
        )
        == "ok"
    )


def test_classify_timeout():
    assert (
        classify_failure(
            -9, cpu_seconds=101, cpu_limit=100, peak_rss=1_000, ram_limit=10_000
        )
        == "timeout"
    )


def test_classify_oom():
    assert (
        classify_failure(
            -9, cpu_seconds=5, cpu_limit=100, peak_rss=9_800, ram_limit=10_000
        )
        == "oom"
    )


def test_classify_crash():
    assert (
        classify_failure(
            1, cpu_seconds=5, cpu_limit=100, peak_rss=1_000, ram_limit=10_000
        )
        == "crash"
    )


def test_render_output_is_grep_stable():
    text = render_output(
        tier="t1",
        status="ok",
        score_bytes=110_793_128,
        archive_bytes=110_351_665,
        binary_bytes=441_463,
        cpu_seconds_comp=100.0,
        cpu_seconds_decomp=200.0,
        peak_rss_bytes=9_000_000_000,
        projected_prize_hours=64.8,
        roundtrip_ok=True,
    )
    lines = text.splitlines()
    assert "score_bytes: 110793128" in lines
    assert "status: ok" in lines
    assert "roundtrip_ok: true" in lines
    assert "projected_prize_hours: 64.80" in lines
