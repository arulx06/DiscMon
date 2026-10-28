from __future__ import annotations

import calendar
import re
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from dateutil import parser as date_parser

from app.db.models.enums import DeadlinePrecision

IST = ZoneInfo("Asia/Kolkata")
UTC = UTC

ISO_DATE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
ISO_DATETIME = re.compile(
    r"\b(20\d{2})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?(Z|[+-]\d{2}:?\d{2})?\b"
)
MONTH_DAY = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(20\d{2}))?\b",
    re.IGNORECASE,
)
DAY_MONTH = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"(?:,?\s+(20\d{2}))?\b",
    re.IGNORECASE,
)
MONTH_YEAR = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(20\d{2})\b",
    re.IGNORECASE,
)

MONTHS = {name.lower(): index for index, name in enumerate(calendar.month_name) if name}


def now_utc() -> datetime:
    return datetime.now(tz=UTC)


def ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = date_parser.parse(value)
    except (ValueError, OverflowError):
        return None
    return ensure_utc(parsed)


def parse_date_only(value: str | None) -> date | None:
    if not value:
        return None
    match = ISO_DATE.search(value)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None
    parsed = parse_datetime(value)
    return parsed.date() if parsed else None


def parse_deadline_text(text: str | None, reference: datetime | None = None) -> dict:
    """Parse a deadline without inventing a cutoff time.

    Returns keys: deadline_on, deadline_at, deadline_timezone, deadline_precision.
    A date-only value intentionally leaves deadline_at as None.
    """
    result: dict[str, object] = {
        "deadline_on": None,
        "deadline_at": None,
        "deadline_timezone": None,
        "deadline_precision": DeadlinePrecision.unknown,
    }
    if not text:
        return result
    normalized = text.strip()

    match = ISO_DATETIME.search(normalized)
    if match:
        year, month, day, hour, minute = (int(match.group(i)) for i in range(1, 6))
        second = int(match.group(6) or 0)
        tz_value = match.group(7)
        if tz_value:
            tzinfo = (
                UTC
                if tz_value == "Z"
                else datetime.fromisoformat(f"2000-01-01T00:00:00{tz_value}").tzinfo
            )
            dt = datetime(year, month, day, hour, minute, second, tzinfo=tzinfo).astimezone(UTC)
            result.update(
                deadline_on=dt.date(),
                deadline_at=dt,
                deadline_timezone=str(tzinfo),
                deadline_precision=DeadlinePrecision.exact,
            )
            return result

    match = ISO_DATE.search(normalized)
    if match:
        year, month, day = (int(match.group(i)) for i in range(1, 4))
        try:
            parsed_date = date(year, month, day)
        except ValueError:
            return result
        result.update(
            deadline_on=parsed_date,
            deadline_at=None,
            deadline_timezone=None,
            deadline_precision=DeadlinePrecision.date_only,
        )
        return result

    ref = reference or now_utc()
    ref_year = ref.year

    match = MONTH_DAY.search(normalized)
    if not match:
        match = DAY_MONTH.search(normalized)
        if match:
            day_value, month_name, year_value = match.group(1), match.group(2), match.group(3)
        else:
            month_year = MONTH_YEAR.search(normalized)
            if month_year:
                month_number = MONTHS[month_year.group(1).lower()]
                result.update(
                    deadline_on=date(int(month_year.group(2)), month_number, 1),
                    deadline_at=None,
                    deadline_timezone=None,
                    deadline_precision=DeadlinePrecision.month_only,
                )
            return result
    else:
        month_name, day_value, year_value = match.group(1), match.group(2), match.group(3)

    month_number = MONTHS[month_name.lower()]
    day_number = int(day_value)
    if year_value:
        year_number = int(year_value)
    else:
        year_number = ref_year
        try:
            candidate = date(year_number, month_number, day_number)
        except ValueError:
            return result
        if candidate < ref.date() - timedelta(days=1):
            year_number += 1
    try:
        parsed_date = date(year_number, month_number, day_number)
    except ValueError:
        return result
    result.update(
        deadline_on=parsed_date,
        deadline_at=None,
        deadline_timezone=None,
        deadline_precision=DeadlinePrecision.date_only,
    )
    return result


DEADLINE_CONTEXT_PATTERN = re.compile(
    r"(?:application\s+deadline|deadline(?:\s+to\s+apply)?|applications?\s+(?:close|closes|due|must\s+be\s+submitted)|"
    r"apply\s+(?:by|before)|submissions?\s+(?:close|due)|closes?\s+(?:on|at|by)|closing\s+date|"
    r"last\s+date\s+to\s+apply|open\s+until|due\s+(?:by|on))",
    re.IGNORECASE,
)


def extract_deadline_from_text(text: str | None, reference: datetime | None = None) -> dict:
    """Only use date text adjacent to an explicit deadline phrase."""
    result: dict[str, object] = {
        "deadline_on": None,
        "deadline_at": None,
        "deadline_timezone": None,
        "deadline_precision": DeadlinePrecision.unknown,
    }
    if not text:
        return result
    for match in DEADLINE_CONTEXT_PATTERN.finditer(text):
        window = text[match.start() : match.start() + 180]
        parsed = parse_deadline_text(window, reference)
        if parsed["deadline_precision"] != DeadlinePrecision.unknown:
            return parsed
    return result


def deadline_state(
    opens_on: date | None,
    deadline_on: date | None,
    deadline_at: datetime | None,
    reference: date | None = None,
) -> str:
    today = reference or now_utc().date()
    if deadline_at is not None and deadline_at < now_utc():
        return "closed"
    if deadline_on is not None and deadline_on < today:
        return "closed"
    if opens_on is not None and opens_on > today:
        return "upcoming"
    return "open"


def days_until(value: date | datetime | None) -> int | None:
    if value is None:
        return None
    today = now_utc().date()
    target = value.date() if isinstance(value, datetime) else value
    return (target - today).days


def is_within_quiet_hours(now: datetime, start_hour: int, end_hour: int, tz_name: str) -> bool:
    local = now.astimezone(ZoneInfo(tz_name))
    if start_hour == end_hour:
        return False
    if start_hour < end_hour:
        return start_hour <= local.hour < end_hour
    return local.hour >= start_hour or local.hour < end_hour


def next_allowed_slot(now: datetime, start_hour: int, end_hour: int, tz_name: str) -> datetime:
    if not is_within_quiet_hours(now, start_hour, end_hour, tz_name):
        return now
    local = now.astimezone(ZoneInfo(tz_name))
    allowed = local.replace(hour=end_hour, minute=0, second=0, microsecond=0)
    if allowed <= local:
        allowed += timedelta(days=1)
    return allowed.astimezone(UTC)


def combine_date_with_time(value: date, clock: time, tz_name: str) -> datetime:
    return datetime.combine(value, clock, tzinfo=ZoneInfo(tz_name)).astimezone(UTC)
