"""Ledger analytics: deltas vs main baselines and tier correlation.

Usage: uv run report.py
"""

from pathlib import Path

from ledger import read_rows

LEDGER = Path(__file__).resolve().parent / "ledger.tsv"


def baselines(rows: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in rows:
        if r["branch"] == "main" and r["status"] == "ok":
            out[r["tier"]] = r
    return out


def deltas(rows: list[dict]) -> list[dict]:
    base = baselines(rows)
    out = []
    for r in rows:
        if r["branch"] == "main" or r["status"] != "ok":
            continue
        b = base.get(r["tier"])
        if b is None:
            continue
        out.append(
            {
                **r,
                "delta_bytes": int(r["score_bytes"]) - int(b["score_bytes"]),
            }
        )
    return out


def main() -> None:
    rows = read_rows(LEDGER)
    base = baselines(rows)
    print("== baselines (main) ==")
    for tier in sorted(base):
        b = base[tier]
        print(f"{tier}: {b['score_bytes']} bytes  cpu {b['cpu_seconds_comp']}s")
    print()
    print("== experiments ==")
    for r in sorted(deltas(rows), key=lambda r: (r["branch"], r["tier"])):
        sign = "+" if r["delta_bytes"] >= 0 else ""
        print(
            f"{r['branch']:<28} {r['tier']} {r['commit'][:7]} "
            f"{sign}{r['delta_bytes']} bytes  {r['description']}"
        )
    print()
    failed = [r for r in rows if r["status"] != "ok"]
    if failed:
        print("== failures ==")
        for r in failed:
            print(f"{r['branch']:<28} {r['tier']} {r['commit'][:7]} {r['status']}")


if __name__ == "__main__":
    main()
