from datetime import UTC, datetime


def utcnow() -> datetime:
    now = datetime.now(UTC)
    millis = (now.microsecond // 1000) * 1000
    return now.replace(microsecond=millis)


def to_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    else:
        value = value.astimezone(UTC)
    millis = value.microsecond // 1000
    return value.strftime("%Y-%m-%dT%H:%M:%S.") + f"{millis:03d}Z"
