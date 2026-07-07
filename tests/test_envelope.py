import pytest

from envelope import (
    RAM_LIMIT_BYTES,
    cpu_budget_seconds,
    load_geekbench_t,
    load_machine_config,
    projected_prize_hours,
    tier_cpu_limit_seconds,
)


def test_ram_limit_is_decimal_10gb():
    assert RAM_LIMIT_BYTES == 10_000_000_000


def test_cpu_budget_scales_inversely_with_geekbench():
    assert cpu_budget_seconds(1026) == pytest.approx(70_000 / 1026 * 3600)
    assert cpu_budget_seconds(2052) == pytest.approx(cpu_budget_seconds(1026) / 2)


def test_tier_limits():
    assert tier_cpu_limit_seconds("t0", 1000) == 2 * 3600
    assert tier_cpu_limit_seconds("t1", 1000) == 12 * 3600
    assert tier_cpu_limit_seconds("t2", 1000) == pytest.approx(70_000 / 1000 * 3600)
    with pytest.raises(ValueError):
        tier_cpu_limit_seconds("t9", 1000)


def test_projected_prize_hours_matches_fx2_reference():
    assert projected_prize_hours(64.8 * 3600, 1026) == pytest.approx(64.8)
    assert projected_prize_hours(32.4 * 3600, 2052) == pytest.approx(64.8)


def test_load_geekbench_t(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("geekbench5_single_core = 1800\n")
    assert load_geekbench_t(cfg) == 1800.0
    cfg.write_text("geekbench5_single_core = 0\n")
    with pytest.raises(ValueError):
        load_geekbench_t(cfg)


def test_machine_config_defaults(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("geekbench5_single_core = 1800\n")
    m = load_machine_config(cfg)
    assert m.pin_cpu is None
    assert m.ram_enforcer == "systemd-run"
    assert m.march_override is None


def test_machine_config_march_override(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('geekbench5_single_core = 1800\nmarch_override = "raptorlake"\n')
    assert load_machine_config(cfg).march_override == "raptorlake"


def test_machine_config_explicit(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        'geekbench5_single_core = 750\npin_cpu = 2\nram_enforcer = "external"\n'
    )
    m = load_machine_config(cfg)
    assert m.geekbench_t == 750.0
    assert m.pin_cpu == 2
    assert m.ram_enforcer == "external"


def test_machine_config_rejects_unknown_enforcer(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('geekbench5_single_core = 750\nram_enforcer = "docker"\n')
    with pytest.raises(ValueError):
        load_machine_config(cfg)
