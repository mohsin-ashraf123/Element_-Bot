"""Send test messages to the Element room."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.services import matrix_client, round_service, team_service
from app.services.report_service import (
    build_report_caption,
    build_report_image,
    preview_report,
)
from app.db.models import ElementEvent


def _log_event(
    db: Session,
    *,
    kind: str,
    text: str,
    event_id: str | None,
    status: str,
    error: str | None = None,
    round_id: int | None = None,
) -> None:
    row = ElementEvent(
        kind=kind,
        rendered_text=text,
        matrix_event_id=event_id,
        status=status,
        sent_at=datetime.now(timezone.utc) if status == "sent" else None,
        error=error,
        round_id=round_id,
    )
    db.add(row)
    db.commit()


def send_pairs(db: Session) -> dict:
    preview = round_service.preview_round(db, date.today())
    text = preview["rendered_text"]
    try:
        event_id = matrix_client.send_text(text)
        rnd = round_service.persist_round(db, date.today(), status="sent", rendered_text=text)
        _log_event(
            db,
            kind="daily_message",
            text=text,
            event_id=event_id,
            status="sent",
            round_id=rnd.id,
        )
        from app.services import matrix_room_feed

        matrix_room_feed.invalidate_cache()
        try:
            from app.db.session import SessionLocal
            from app.services import dashboard_service
            from app.services.feed_hub import notify_feed_update

            db = SessionLocal()
            try:
                notify_feed_update(dashboard_service.build_feed(db), force=True)
            finally:
                db.close()
        except Exception:
            pass
        return {
            "ok": True,
            "kind": "pairs",
            "event_id": event_id,
            "round_id": rnd.id,
            "text": text,
            "message": "Pairs message sent to Element room",
        }
    except Exception as exc:
        _log_event(
            db,
            kind="daily_message",
            text=text,
            event_id=None,
            status="failed",
            error=str(exc),
        )
        return {"ok": False, "kind": "pairs", "text": text, "error": str(exc)}


def send_report(db: Session, *, period_type: str = "weekly") -> dict:
    """Render HTML table → PNG → encrypted image + AI caption to Element."""
    label = "Weekly" if period_type == "weekly" else "Monthly"
    try:
        from app.services import report_builder_service

        report_builder_service.generate_scoped_report(db, period_type=period_type)  # type: ignore[arg-type]
        png, width, height, ctx = build_report_image(db, period_type=period_type)
        caption = build_report_caption(ctx)
        filename = f"{period_type}-report-{ctx['report_date']}.png"

        caption_id = matrix_client.send_text(caption)
        image_id = matrix_client.send_image(
            png,
            filename=filename,
            width=width,
            height=height,
        )

        log_text = f"{caption}\n[image: {filename} {width}x{height}]"
        _log_event(
            db,
            kind="report_post",
            text=log_text,
            event_id=image_id,
            status="sent",
        )
        try:
            from app.services import dashboard_service, matrix_room_feed
            from app.services.feed_hub import notify_feed_update

            matrix_room_feed.invalidate_cache()
            notify_feed_update(dashboard_service.build_feed(db), force=True)
        except Exception:
            pass
        return {
            "ok": True,
            "kind": "report",
            "event_id": image_id,
            "caption_event_id": caption_id,
            "text": caption,
            "filename": filename,
            "width": width,
            "height": height,
            "message": f"{label} report image sent to Element room",
        }
    except Exception as exc:
        caption = f"{label} report (failed before send)"
        _log_event(
            db,
            kind="report_post",
            text=caption,
            event_id=None,
            status="failed",
            error=str(exc),
        )
        return {"ok": False, "kind": "report", "text": caption, "error": str(exc).strip() or repr(exc)}


def get_report_preview(db: Session) -> dict:
    return preview_report(db)
