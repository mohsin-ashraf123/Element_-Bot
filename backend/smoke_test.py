"""Quick smoke test — run before/after changing .env (room ID, Matrix creds, etc.).

Usage (from backend/):
    .\\venv\\Scripts\\python.exe smoke_test.py
    .\\venv\\Scripts\\python.exe smoke_test.py --force   # bypass Matrix cache
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from app.db.session import SessionLocal
from app.services import dashboard_service, element_health, round_service


def _ok(label: str, passed: bool, detail: str = "") -> None:
    mark = "PASS" if passed else "FAIL"
    line = f"[{mark}] {label}"
    if detail:
        line += f" — {detail}"
    print(line)


def main() -> int:
    parser = argparse.ArgumentParser(description="PairFlow smoke test")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force fresh Matrix login (ignore cache)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print raw JSON instead of human-readable output",
    )
    args = parser.parse_args()

    element = element_health.check(force=args.force)
    db = SessionLocal()
    try:
        status = dashboard_service.build_status(db)
        preview = round_service.preview_round(db, date.today())
    finally:
        db.close()

    if args.json:
        print(
            json.dumps(
                {"element": element, "status": status, "preview": preview},
                indent=2,
                default=str,
            )
        )
        return 0

    print()
    print("=" * 56)
    print("  PairFlow Smoke Test")
    print("=" * 56)

    print("\n--- Matrix / Room (.env) ---")
    print(f"  Homeserver : {element.get('homeserver')}")
    print(f"  Room ID    : {element.get('room_id')}")
    print(f"  Room label : {element.get('room_label')}")

    _ok("Env configured", element["configured"])
    _ok("Matrix login", element["connected"], element.get("error") or "logged in")
    _ok(
        "Bot joined target room",
        element["joined"],
        "invite @bot to the room if login works but this fails",
    )
    _ok("E2EE store ready", element["e2ee_store_ready"])

    if element.get("error"):
        print(f"  Error: {element['error']}")
    if element.get("cached"):
        print("  (Matrix result served from cache — use --force for fresh check)")

    print("\n--- Dashboard (what UI should show) ---")
    linked = status["element_connected"] and status["element_joined"]
    element_label = "Linked" if linked else ("Configured" if status["element_configured"] else "Not linked")
    print(f"  Element card     : {element_label}")
    print(f"  Active members   : {status['active_members']}")
    print(f"  Config gaps      : {status['config_gaps']}")
    print(f"  Next send (PKT)  : {status['next_send_at']}")
    if status["alerts"]:
        print(f"  Alerts           : {', '.join(status['alerts'])}")

    print("\n--- Today's message preview (expected bot output) ---")
    print(f"  Combo     : {preview['combo_label']}")
    print(f"  Team lead : {preview['team_lead']}")
    print(f"  Pairs     : {len(preview['pairs'])}")
    print()
    print(preview["rendered_text"])
    print()

    all_good = (
        element["configured"]
        and element["connected"]
        and element["joined"]
        and status["database_connected"]
    )
    if all_good:
        print("RESULT: All checks passed — room + pairing preview look good.")
        return 0

    print("RESULT: Some checks failed — fix items marked FAIL above.")
    if element["connected"] and not element["joined"]:
        print(
            "TIP: Login works but bot is NOT in the room. "
            "Open Element → invite the bot to the new room, then re-run."
        )
    if not element["connected"]:
        print("TIP: If device limit — Element → Settings → Sessions → sign out old devices.")
        print("     Or set MATRIX_ACCESS_TOKEN in .env after one manual login.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
