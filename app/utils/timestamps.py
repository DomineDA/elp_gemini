"""DB의 naive UTC datetime을 오프셋 붙은 ISO 문자열로 직렬화한다 (#163)."""

from datetime import datetime, timezone


def utc_iso(value: datetime | None) -> str | None:
    """naive는 UTC로 간주하고, aware는 UTC로 변환해 '+00:00'을 붙인다."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()
