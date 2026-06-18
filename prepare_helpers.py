"""Stand-alone helpers required by prepare and tests."""


def expected_enwik9_size_bytes() -> int:
    return 1_000_000_000


def proxy_offset(total_size: int, slice_size: int) -> int:
    """Start offset of a single contiguous proxy slice taken from the middle.

    A contiguous slice (rather than disjoint chunks) preserves long-range match
    structure, and the middle avoids the unrepresentative XML preamble at offset 0.
    """
    if total_size <= 0:
        raise ValueError("total_size must be positive")
    if slice_size <= 0 or slice_size > total_size:
        raise ValueError("slice_size must be in range (0, total_size]")

    return (total_size - slice_size) // 2
