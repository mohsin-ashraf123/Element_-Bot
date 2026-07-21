"""Isolated Playwright worker — spawned as a subprocess to avoid asyncio loop conflicts."""

from __future__ import annotations

import base64
import json
import sys


def main() -> None:
    html = sys.stdin.read()
    if not html.strip():
        raise SystemExit("empty HTML input")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit(
            "Playwright is required. Run: pip install playwright && playwright install chromium"
        ) from exc

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(
                viewport={"width": 900, "height": 1200},
                device_scale_factor=2,
            )
            page.set_content(html, wait_until="load")
            card = page.locator(".report-doc")
            box = card.bounding_box()
            if not box:
                raise RuntimeError("Report card not found in HTML")
            png = card.screenshot(type="png")
            payload = {
                "png_b64": base64.b64encode(png).decode("ascii"),
                "width": int(box["width"]),
                "height": int(box["height"]),
            }
            sys.stdout.write(json.dumps(payload))
        finally:
            browser.close()


if __name__ == "__main__":
    main()
