"""Stand-alone helpers required by prepare and tests."""


def expected_enwik9_size_bytes() -> int:
    return 1_000_000_000


def proxy_offsets(total_size: int, slice_size: int) -> list[int]:
    if total_size <= 0:
        raise ValueError("total_size must be positive")
    if slice_size <= 0 or slice_size > total_size:
        raise ValueError("slice_size must be in range (0, total_size]")

    middle = (total_size - slice_size) // 2
    tail = total_size - slice_size
    return [0, middle, tail]
