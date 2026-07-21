"""Tests for the daily send scheduler."""

from datetime import date, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.domain.calendar import tz
from app.services.scheduler_service import is_due


def test_is_due_after_send_time_on_working_day():
    schedule = {
        "send_time": "10:54",
        "working_days": ["mon", "tue", "wed", "thu", "fri"],
        "timezone": "Asia/Karachi",
    }
    pkt = ZoneInfo("Asia/Karachi")
    # Thursday Jul 16 2026 10:56 PKT — past 10:54
    fake_now = datetime(2026, 7, 16, 10, 56, tzinfo=pkt)

    with patch("app.services.scheduler_service.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        mock_dt.combine = datetime.combine
        assert is_due(schedule) is True


def test_is_due_false_before_send_time():
    schedule = {
        "send_time": "11:00",
        "working_days": ["mon", "tue", "wed", "thu", "fri"],
        "timezone": "Asia/Karachi",
    }
    pkt = ZoneInfo("Asia/Karachi")
    fake_now = datetime(2026, 7, 16, 10, 30, tzinfo=pkt)

    with patch("app.services.scheduler_service.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        mock_dt.combine = datetime.combine
        assert is_due(schedule) is False
