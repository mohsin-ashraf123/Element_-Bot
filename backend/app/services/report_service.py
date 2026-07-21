"""HTML report table → PNG screenshot for Element room posts."""

from __future__ import annotations

import base64
from datetime import date
from html import escape
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services import report_builder_service


def _pct_class(val: str) -> str:
    if val == "—":
        return "mid"
    try:
        n = float(val.rstrip("%"))
        if n >= 80:
            return "hi"
        if n >= 50:
            return "mid"
        return "lo"
    except ValueError:
        return "mid"


def build_report_context(
    db: Session,
    *,
    report_date: date | None = None,
    period_type: str = "weekly",
) -> dict[str, Any]:
    """Gather real metrics + optional saved AI analysis for the period."""
    metrics = report_builder_service.build_metrics_payload(
        db, period_type=period_type, ref=report_date  # type: ignore[arg-type]
    )
    saved = report_builder_service.latest_report(db, period_type)  # type: ignore[arg-type]
    ai = (saved or {}).get("ai_analysis") or metrics.get("ai_analysis") or {}

    rows: list[dict[str, str]] = []
    for m in metrics.get("members", []):
        role = "Dev" if m.get("role") == "DEVELOPER" else "QA"
        rows.append(
            {
                "name": m["name"],
                "role": role,
                "done": f"{m['completion_rate']}%",
                "ontime": f"{m['on_time_rate']}%",
                "clean": f"{m['clean_rate']}%",
                "streak": str(m.get("current_streak", 0)),
            }
        )

    narrative = (
        ai.get("narrative_short")
        or ai.get("executive_summary")
        or (saved or {}).get("narrative")
        or ""
    )

    return {
        "title": "Weekly Performance" if period_type == "weekly" else "Monthly Performance",
        "room_label": settings.matrix_room_id or "Element room",
        "period_label": metrics["period_label"],
        "period_days": metrics.get("record_count", 0) or "—",
        "period_type": period_type,
        "report_date": (report_date or date.today()).isoformat(),
        "member_count": len(rows),
        "rows": rows,
        "ingestion_live": metrics.get("ingestion_live", False),
        "team_completion": metrics["team"]["completion_rate"],
        "team_on_time": metrics["team"]["on_time_rate"],
        "team_clean": metrics["team"]["clean_rate"],
        "narrative": narrative,
        "ai_analysis": ai,
        "narrative_source": (saved or {}).get("narrative_source"),
    }


def render_report_html(ctx: dict[str, Any]) -> str:
    """Self-contained HTML matching the PairFlow report-doc design."""
    rows_html = "\n".join(
        f"""<tr>
          <td>{escape(r['name'])}</td>
          <td>{escape(r['role'])}</td>
          <td class="pct {_pct_class(r['done'])}">{escape(r['done'])}</td>
          <td class="pct {_pct_class(r['ontime'])}">{escape(r['ontime'])}</td>
          <td class="pct {_pct_class(r['clean'])}">{escape(r['clean'])}</td>
          <td>{escape(r['streak'])}</td>
        </tr>"""
        for r in ctx["rows"]
    ) or '<tr><td colspan="6" style="text-align:center;color:#8e8e93">No active members</td></tr>'

    banner = ""
    if not ctx.get("ingestion_live"):
        banner = (
            '<div class="banner">Limited performance data for this period — metrics fill in '
            "as daily reports are ingested.</div>"
        )

    ai_block = ""
    narrative = (ctx.get("narrative") or "").strip()
    if narrative:
        src = ctx.get("narrative_source") or "template"
        label = "AI summary" if src == "llm" else "Summary"
        ai_block = f"""
    <div class="ai-block">
      <div class="ai-label">{escape(label)}</div>
      <div class="ai-text">{escape(narrative)}</div>
    </div>"""

    team_stats = ""
    if ctx.get("ingestion_live"):
        team_stats = f"""
    <div class="team-stats">
      <span><b>Team done</b> {ctx.get('team_completion', 0)}%</span>
      <span><b>On-time</b> {ctx.get('team_on_time', 0)}%</span>
      <span><b>Clean</b> {ctx.get('team_clean', 0)}%</span>
    </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #f2f2f7;
      padding: 28px;
      display: flex;
      justify-content: center;
    }}
    .report-doc {{
      background: #fff;
      border: 1px solid rgba(0,0,0,.08);
      border-radius: 14px;
      overflow: hidden;
      box-shadow: 0 8px 28px rgba(0,0,0,.08);
      width: 720px;
      color: #1d1d1f;
    }}
    .rd-head {{
      background: linear-gradient(135deg, #0A84FF, #5E5CE6);
      padding: 16px 20px;
      color: #fff;
    }}
    .rd-head b {{ font-size: 16px; font-weight: 650; display: block; }}
    .rd-head small {{ opacity: .92; font-size: 12px; }}
    .banner {{
      margin: 12px 18px 0;
      padding: 10px 12px;
      border-radius: 10px;
      background: #fff8e6;
      border: 1px solid #ffe08a;
      color: #8a6d00;
      font-size: 11.5px;
      font-weight: 500;
    }}
    .rd-body {{ padding: 14px 20px 10px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 12.5px; }}
    th {{
      color: #8e8e93;
      text-align: left;
      font-size: 10.5px;
      text-transform: uppercase;
      letter-spacing: .03em;
      padding: 0 8px 10px;
      font-weight: 600;
    }}
    td {{
      padding: 10px 8px;
      border-top: 1px solid rgba(0,0,0,.07);
      font-weight: 500;
    }}
    tr td:first-child {{ font-weight: 650; }}
    .pct {{ font-weight: 600; }}
    .pct.hi {{ color: #34C759; }}
    .pct.mid {{ color: #FF9F0A; }}
    .pct.lo {{ color: #FF3B30; }}
    .rd-foot {{
      padding: 11px 20px;
      border-top: 1px solid rgba(0,0,0,.07);
      font-size: 11px;
      color: #8e8e93;
      font-weight: 500;
    }}
    .ai-block {{
      margin: 12px 18px 0;
      padding: 12px 14px;
      border-radius: 10px;
      background: #f0f7ff;
      border: 1px solid #c7e0ff;
    }}
    .ai-label {{
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: .04em;
      color: #0A84FF;
      font-weight: 700;
      margin-bottom: 6px;
    }}
    .ai-text {{
      font-size: 12px;
      line-height: 1.5;
      color: #1d1d1f;
    }}
    .team-stats {{
      display: flex;
      gap: 16px;
      margin: 0 18px 10px;
      font-size: 11.5px;
      color: #636366;
    }}
    .team-stats b {{ color: #1d1d1f; }}
  </style>
</head>
<body>
  <div class="report-doc">
    <div class="rd-head">
      <b>{escape(ctx['title'])} · PairFlow</b>
      <small>{escape(ctx['period_label'])} · {ctx['period_days']} day records</small>
    </div>
    {banner}
    {team_stats}
    <div class="rd-body">
      <table>
        <tr>
          <th>Member</th><th>Role</th><th>Done</th><th>On-time</th><th>Clean</th><th>Streak</th>
        </tr>
        {rows_html}
      </table>
    </div>
    {ai_block}
    <div class="rd-foot">
      {ctx['member_count']} members tracked · generated by PairFlow · {escape(ctx['report_date'])}
    </div>
  </div>
</body>
</html>"""


def render_report_png(html: str) -> tuple[bytes, int, int]:
    """Screenshot the report card; returns (png_bytes, width, height).

    Playwright is run in a child process so it works under uvicorn --reload on
    Windows (the reloader's asyncio loop cannot spawn Playwright's driver).
    """
    import base64
    import json
    import subprocess
    import sys
    from pathlib import Path

    backend_root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [sys.executable, "-m", "app.services._report_screenshot_worker"],
        input=html,
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(backend_root),
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "Report screenshot failed").strip()
        raise RuntimeError(detail)

    try:
        payload = json.loads(proc.stdout)
        png = base64.b64decode(payload["png_b64"])
        return png, int(payload["width"]), int(payload["height"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("Invalid screenshot worker output") from exc


def build_report_image(
    db: Session,
    *,
    period_type: str = "weekly",
) -> tuple[bytes, int, int, dict[str, Any]]:
    ctx = build_report_context(db, period_type=period_type)
    html = render_report_html(ctx)
    png, w, h = render_report_png(html)
    return png, w, h, ctx


def build_report_caption(ctx: dict[str, Any]) -> str:
    narrative = (ctx.get("narrative") or "").strip()
    header = (
        f"📊 {'Weekly' if ctx.get('period_type') == 'weekly' else 'Monthly'} report — "
        f"{ctx['period_label']}"
    )
    if narrative:
        return f"{header}\n\n{narrative[:500]}"
    return (
        f"{header}\n"
        f"Team completion: {ctx.get('team_completion', 0)}% · "
        f"On-time: {ctx.get('team_on_time', 0)}% · "
        f"Clean: {ctx.get('team_clean', 0)}%"
    )


def preview_report(db: Session) -> dict[str, Any]:
    png, w, h, ctx = build_report_image(db)
    return {
        "caption": build_report_caption(ctx),
        "period_label": ctx["period_label"],
        "width": w,
        "height": h,
        "image_base64": base64.b64encode(png).decode("ascii"),
        "member_count": ctx["member_count"],
    }
