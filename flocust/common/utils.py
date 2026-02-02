"""Shared utilities used across flocust modules."""


def percentile(sorted_values: list[float], p: float) -> float:
    """Return p-th percentile (0-100). Linear interpolation between neighbors."""
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * (p / 100)
    f = int(k)
    c = 1 if f < len(sorted_values) - 1 else 0
    return sorted_values[f] * (1 - (k - f)) + sorted_values[f + c] * (k - f)
