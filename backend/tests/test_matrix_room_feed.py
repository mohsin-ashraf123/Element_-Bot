"""Unit tests for room feed helpers."""

from __future__ import annotations

import json
from pathlib import Path

import app.services.matrix_room_feed as feed


def test_merge_member_cache_adds_persisted_member(tmp_path, monkeypatch):
    cache_file = tmp_path / "member_feed_cache.json"
    monkeypatch.setattr(feed, "_MEMBER_CACHE_PATH", cache_file)

    room_id = "!room:matrix.org"
    cache_file.write_text(
        json.dumps(
            {
                room_id: {
                    "$evt1": {
                        "id": "$evt1",
                        "event_id": "$evt1",
                        "kind": "room_message",
                        "label": "Mohsin",
                        "sender": "@mohsinashraf:matrix.org",
                        "text": "Faz + Hamza: Review completed.",
                        "sent_at": "2026-07-16T14:05:00+05:00",
                        "is_bot": False,
                        "day": "2026-07-16",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    bot_only = [
        {
            "id": "$bot1",
            "event_id": "$bot1",
            "kind": "report_post",
            "label": "PairFlow bot",
            "sender": "@bot_dtrader:matrix.org",
            "text": "Weekly report",
            "sent_at": "2026-07-16T13:00:00+05:00",
            "is_bot": True,
        }
    ]

    monkeypatch.setattr(
        feed,
        "_member_cache_for_room",
        lambda room, day: [
            {
                "id": "$evt1",
                "event_id": "$evt1",
                "kind": "room_message",
                "label": "Mohsin",
                "sender": "@mohsinashraf:matrix.org",
                "text": "Faz + Hamza: Review completed.",
                "sent_at": "2026-07-16T14:05:00+05:00",
                "is_bot": False,
                "day": day,
            }
        ],
    )

    merged = feed.merge_member_cache(room_id, bot_only, zone_name="Asia/Karachi")
    assert len(merged) == 2
    assert any(not m["is_bot"] for m in merged)
    assert any(m["label"] == "Mohsin" for m in merged)


def test_feed_incomplete_without_members():
    assert feed.feed_incomplete([{"is_bot": True, "text": "hi"}])
    assert not feed.feed_incomplete(
        [{"is_bot": True}, {"is_bot": False, "text": "member msg"}]
    )
