"""Tests for pairing-room attendance inference."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.analysis_service import _build_member_rows, _pair_header_names


def test_pair_header_names_with_colon():
    assert _pair_header_names(
        "Faz + Uzair:\nReview completed. No issues, concerns, or improvement recommendations identified."
    ) == ["Faz", "Uzair"]


def test_pair_header_names_with_newline():
    assert _pair_header_names(
        "Saad + Hamza + Farhan\nReview completed. No issues, concerns, or improvement recommendations identified."
    ) == ["Saad", "Hamza", "Farhan"]


def test_group_report_credits_all_pair_members():
    pairing_messages = [
        {
            "id": 1,
            "is_bot": False,
            "sender": "@fazkhalid:matrix.org",
            "text": (
                "Faz + Uzair:\n"
                "Review completed. No issues, concerns, or improvement recommendations identified."
            ),
            "sent_at": "2026-07-20T13:55:00+00:00",
            "event_id": "e1",
        },
        {
            "id": 2,
            "is_bot": False,
            "sender": "@ameerhamza2:matrix.org",
            "text": (
                "Saad + Hamza + Farhan\n"
                "Review completed. No issues, concerns, or improvement recommendations identified."
            ),
            "sent_at": "2026-07-20T14:10:00+00:00",
            "event_id": "e2",
        },
    ]

    members = [
        SimpleNamespace(id=1, name="Uzair", matrix_user_id="@uzair:matrix.org", active=True),
        SimpleNamespace(id=2, name="Saad", matrix_user_id="@saad:matrix.org", active=True),
        SimpleNamespace(id=3, name="Faz", matrix_user_id="@fazkhalid:matrix.org", active=True),
        SimpleNamespace(id=4, name="Hamza", matrix_user_id="@ameerhamza2:matrix.org", active=True),
        SimpleNamespace(id=5, name="Habiba", matrix_user_id="@habiba:matrix.org", active=True),
        SimpleNamespace(id=6, name="Aqeel", matrix_user_id="@aqeel:matrix.org", active=True),
        SimpleNamespace(id=7, name="Farhan", matrix_user_id="@farhan:matrix.org", active=True),
    ]

    db = MagicMock()
    db.scalar.return_value = None

    with (
        patch("app.services.analysis_service.settings_service.get_setting", return_value={"timeliness_cutoff": "23:59"}),
        patch("app.services.analysis_service.round_service.preview_round", return_value={"pairs": []}),
        patch("app.services.analysis_service.team_service.list_members", return_value=members),
        patch("app.services.analysis_service._persist_record"),
    ):
        rows = _build_member_rows(
            db,
            pairing_messages=pairing_messages,
            task_messages=[],
            zone_name="Asia/Karachi",
            round_date=date(2026, 7, 20),
        )

    by_name = {r["name"]: r for r in rows}
    for name in ("Uzair", "Saad", "Faz", "Hamza", "Farhan"):
        assert by_name[name]["completed"] is True, name
        assert by_name[name]["outcome"] == "clean", name
    for name in ("Habiba", "Aqeel"):
        assert by_name[name]["completed"] is False, name
