import csv
from pathlib import Path

COLUMNS = [
    "commit",
    "branch",
    "tier",
    "status",
    "score_bytes",
    "archive_bytes",
    "binary_bytes",
    "cpu_seconds_comp",
    "cpu_seconds_decomp",
    "peak_rss_bytes",
    "projected_prize_hours",
    "description",
]


def append_row(path: Path, row: dict[str, str]) -> None:
    write_header = not path.exists()
    with path.open("a", newline="") as f:
        w = csv.DictWriter(f, COLUMNS, delimiter="\t")
        if write_header:
            w.writeheader()
        w.writerow(row)


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def scored_keys(rows: list[dict[str, str]]) -> set[tuple[str, str]]:
    return {(r["commit"], r["tier"]) for r in rows}
