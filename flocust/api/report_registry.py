"""
In-memory registry for full report file paths (report_id -> temp path).

Used to serve GET /api/report after background write. Entries expire after TTL.
Thread-safe for use from FastAPI endpoints and background tasks.
"""

import time
from pathlib import Path
from threading import Lock

# TTL in seconds; reports expire after 1 hour.
REPORT_TTL_SECONDS = 3600

_registry: dict[str, tuple[Path, float]] = {}
_lock = Lock()


def register(report_id: str, path: Path) -> None:
    """Register a report file path. Overwrites if report_id exists."""
    with _lock:
        _registry[report_id] = (path, time.monotonic())


def get_path(report_id: str) -> Path | None:
    """
    Return the file path for report_id if present and not expired.
    Does not remove the entry; caller may pop after sending.
    """
    with _lock:
        entry = _registry.get(report_id)
        if not entry:
            return None
        path, created = entry
        if time.monotonic() - created > REPORT_TTL_SECONDS:
            del _registry[report_id]
            return None
        return path


def pop_path(report_id: str) -> Path | None:
    """Remove and return the path for report_id, or None if missing/expired."""
    with _lock:
        entry = _registry.pop(report_id, None)
        if not entry:
            return None
        path, created = entry
        if time.monotonic() - created > REPORT_TTL_SECONDS:
            return None
        return path


def remove(report_id: str) -> None:
    """Remove report_id from registry (e.g. after cleanup)."""
    with _lock:
        _registry.pop(report_id, None)
