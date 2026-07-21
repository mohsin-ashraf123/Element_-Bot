"""Domain constants and shared enums."""

from enum import Enum


class Role(str, Enum):
    DEVELOPER = "DEVELOPER"
    QA = "QA"


class PairType(str, Enum):
    DEV = "DEV"
    QA = "QA"
    SOLO = "SOLO"


class Outcome(str, Enum):
    CLEAN = "clean"
    HAS_ISSUES = "has_issues"
    UNDETERMINED = "undetermined"
    MISSED = "missed"


class RoundStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    SEND_FAILED = "send_failed"


# The one canonical "clean" report message (RULES R14.3). Matching is
# case- and whitespace-normalised before comparison.
CLEAN_REPORT_MESSAGE = (
    "Review completed. No issues, concerns, or improvement "
    "recommendations identified."
)

# Default day-of-week codes for working days (RULES R9.3).
WEEKDAY_CODES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DEFAULT_WORKING_DAYS = ["mon", "tue", "wed", "thu", "fri"]
