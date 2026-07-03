from __future__ import annotations

import datetime as dt
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scrapy.http import Response


def _decoded_header(response: Response, name: str) -> str | None:
    """Return the stripped UTF-8 value of the *name* header of *response*, or
    ``None`` if it is absent or not valid UTF-8."""
    raw = response.headers.get(name)
    if not raw:
        return None
    try:
        return raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        return None


def _parse_retry_after(response: Response) -> float | None:
    value = _decoded_header(response, "Retry-After")
    if value is None:
        return None
    if value.isdigit():
        return float(value)  # seconds
    try:
        date = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if date.tzinfo is None:
        date = date.replace(tzinfo=dt.timezone.utc)
    now = dt.datetime.now(dt.timezone.utc)
    seconds_to_wait = (date - now).total_seconds()
    # Keep sub-second precision (a date less than a second away must not be
    # truncated to 0 and dropped); a past or present date yields no delay.
    return max(0.0, seconds_to_wait) or None


def _parse_ratelimit_reset(response: Response) -> float | None:
    value = _decoded_header(response, "RateLimit-Reset")
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None
