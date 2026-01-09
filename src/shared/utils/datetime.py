"""
UTC datetime utilities for consistent timezone handling.

All datetime values in the system should be timezone-aware UTC.
Use these helpers instead of datetime.now() or datetime.utcnow().
"""

from datetime import UTC, datetime, timezone


def utc_now() -> datetime:
    """
    Return the current UTC datetime with timezone info.

    Use this instead of:
        - datetime.now() - naive, uses local timezone
        - datetime.utcnow() - naive, deprecated in Python 3.12
        - datetime.now(UTC) - correct but verbose

    Returns:
        Timezone-aware datetime in UTC
    """
    return datetime.now(UTC)


def ensure_utc(dt: datetime | None) -> datetime | None:
    """
    Ensure a datetime is UTC-aware.

    - If None, returns None
    - If naive, assumes UTC and attaches timezone
    - If aware, converts to UTC

    Use at repository/persistence boundaries to normalize datetimes.

    Args:
        dt: A datetime that may be naive or aware

    Returns:
        UTC-aware datetime or None
    """
    if dt is None:
        return None

    if dt.tzinfo is None:
        # Naive datetime - assume it's UTC and attach timezone
        return dt.replace(tzinfo=UTC)

    # Aware datetime - convert to UTC
    return dt.astimezone(UTC)


def from_timestamp_utc(timestamp: float) -> datetime:
    """
    Create a UTC-aware datetime from a Unix timestamp.

    Use instead of datetime.fromtimestamp() which returns naive local time.

    Args:
        timestamp: Unix timestamp (seconds since epoch)

    Returns:
        UTC-aware datetime
    """
    return datetime.fromtimestamp(timestamp, tz=UTC)


def from_timestamp_ms_utc(timestamp_ms: int) -> datetime:
    """
    Create a UTC-aware datetime from a millisecond Unix timestamp.

    Common in JavaScript/APIs that use milliseconds.

    Args:
        timestamp_ms: Unix timestamp in milliseconds

    Returns:
        UTC-aware datetime
    """
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
