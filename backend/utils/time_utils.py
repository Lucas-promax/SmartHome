from datetime import datetime, timezone


def now_iso() -> str:
    """Return an ISO timestamp with local timezone information."""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
