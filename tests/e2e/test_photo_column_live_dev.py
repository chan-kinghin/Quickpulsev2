"""Live-dev verification of the 照片 column + photo lightbox modal.

Assumes uvicorn is already running on $E2E_BASE_URL (defaults to
http://localhost:8000) and that the running code has Wave A-D changes
merged. Goes through the real login form, fires a real MTO query, and
asserts the photo column + modal flow works end to end against live
Kingdee.

Run with:
    E2E_BASE_URL=http://127.0.0.1:8005 pytest \
        tests/e2e/test_photo_column_live_dev.py --run-e2e -v

Skip silently if the server is not up.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
import requests
from playwright.sync_api import Page, expect


BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:8000")
# DS264102S has 8 production orders with photos populated (verified
# against live Kingdee on 2026-05-11 — see scripts/_probe_output/).
MTO_NUMBER = "DS264102S"
_SCREENSHOT_DIR = Path(__file__).parent


def _server_alive() -> bool:
    try:
        return requests.get(f"{BASE_URL}/health", timeout=2).status_code == 200
    except requests.RequestException:
        return False


pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not _server_alive(),
        reason=f"Live server not running at {BASE_URL}",
    ),
]


def _login(page: Page) -> None:
    page.goto(f"{BASE_URL}/")
    page.locator("#username").fill("admin")
    page.locator("#password").fill("quickpulse")
    with page.expect_navigation(url=re.compile(r".*/dashboard\.html.*")):
        page.get_by_role("button", name="登录").click()


def test_photo_column_visible_and_badge_rendered(page: Page):
    """End-to-end: real login → live MTO query → 照片 column shows badge."""
    _login(page)

    page.locator("#mto-search").fill(MTO_NUMBER)
    page.keyboard.press("Enter")
    expect(page.get_by_role("heading", name="BOM组件明细")).to_be_visible(timeout=30_000)

    # 1. 照片 column header is present.
    column_present = page.evaluate("""
        () => [...document.querySelectorAll('thead th')]
            .some(th => th.innerText.includes('照片'))
    """)
    assert column_present, "照片 column header must be present"

    # 2. At least one row shows a 📷×N badge (DS264102S has 8 PRD_MOs with photos).
    badge_count = page.evaluate("""
        () => [...document.querySelectorAll('tbody tr button')]
            .filter(b => /📷/.test(b.innerText))
            .length
    """)
    assert badge_count > 0, f"No 📷 badges found on rows of MTO {MTO_NUMBER}"

    page.screenshot(
        path=str(_SCREENSHOT_DIR / "photo_column_dev_live_proof.png"),
        full_page=True,
    )
    print(f"\n照片 badges visible: {badge_count} rows")


def test_clicking_badge_opens_modal_and_loads_image(page: Page):
    """Click the first 📷 badge → modal opens, image loads via /api/photo/{id}."""
    _login(page)
    page.locator("#mto-search").fill(MTO_NUMBER)
    page.keyboard.press("Enter")
    expect(page.get_by_role("heading", name="BOM组件明细")).to_be_visible(timeout=30_000)

    # Click first badge containing 📷.
    badge = page.locator("tbody tr button").filter(has_text="📷").first
    expect(badge).to_be_visible(timeout=10_000)
    badge.click()

    # Modal main image must appear and reference /api/photo/{32hex}.
    modal_img = page.locator("div.fixed.inset-0 img").first
    expect(modal_img).to_be_visible(timeout=10_000)
    src = modal_img.get_attribute("src")
    assert src and re.match(r"^/api/photo/[a-f0-9]{32}$", src), (
        f"Modal image src is not a clean /api/photo/{{guid}} URL: {src!r}"
    )

    # Image must actually render (naturalWidth > 0 once decoded).
    page.wait_for_function(
        """() => {
            const img = document.querySelector('div.fixed.inset-0 img');
            return img && img.complete && img.naturalWidth > 0;
        }""",
        timeout=15_000,
    )

    # Modal must still be visible at screenshot time (no inflight close).
    expect(modal_img).to_be_visible()
    page.wait_for_timeout(300)
    page.screenshot(
        path=str(_SCREENSHOT_DIR / "photo_modal_dev_live_proof.png"),
        full_page=True,
    )
    print(f"\nModal main image loaded: {src}")


def test_modal_keyboard_navigation(page: Page):
    """ArrowRight advances, ArrowLeft goes back, Escape closes."""
    _login(page)
    page.locator("#mto-search").fill(MTO_NUMBER)
    page.keyboard.press("Enter")
    expect(page.get_by_role("heading", name="BOM组件明细")).to_be_visible(timeout=30_000)

    badge = page.locator("tbody tr button").filter(has_text="📷").first
    badge.click()

    modal_img = page.locator("div.fixed.inset-0 img").first
    expect(modal_img).to_be_visible(timeout=10_000)
    first_src = modal_img.get_attribute("src")

    # ArrowRight: src must change (multi-photo row).
    page.keyboard.press("ArrowRight")
    page.wait_for_function(
        f"""(prev) => {{
            const img = document.querySelector('div.fixed.inset-0 img');
            return img && img.src && !img.src.endsWith('{first_src.split('/')[-1]}');
        }}""",
        arg=first_src,
        timeout=5_000,
    )
    second_src = modal_img.get_attribute("src")
    assert second_src != first_src, "ArrowRight did not advance image"

    # ArrowLeft: back to first.
    page.keyboard.press("ArrowLeft")
    page.wait_for_function(
        f"""() => {{
            const img = document.querySelector('div.fixed.inset-0 img');
            return img && img.src.endsWith('{first_src.split('/')[-1]}');
        }}""",
        timeout=5_000,
    )

    # Escape closes.
    page.keyboard.press("Escape")
    expect(page.locator("div.fixed.inset-0").filter(has=modal_img)).to_have_count(0, timeout=5_000)
    print("\nKeyboard nav verified: ArrowRight → ArrowLeft → Escape all worked")


def test_photo_response_has_immutable_cache_header(page: Page):
    """Watch the network — /api/photo response must declare immutable cache."""
    _login(page)
    page.locator("#mto-search").fill(MTO_NUMBER)
    page.keyboard.press("Enter")
    expect(page.get_by_role("heading", name="BOM组件明细")).to_be_visible(timeout=30_000)

    captured_headers: dict = {}

    def on_response(resp):
        if "/api/photo/" in resp.url and resp.status == 200:
            captured_headers["url"] = resp.url
            captured_headers["cache_control"] = resp.headers.get("cache-control", "")
            captured_headers["content_type"] = resp.headers.get("content-type", "")

    page.on("response", on_response)

    badge = page.locator("tbody tr button").filter(has_text="📷").first
    badge.click()
    expect(page.locator("div.fixed.inset-0 img").first).to_be_visible(timeout=10_000)

    # Give the network listener a beat to flush.
    page.wait_for_timeout(500)

    assert captured_headers, "No /api/photo response captured"
    cc = captured_headers["cache_control"]
    assert "immutable" in cc, f"Cache-Control missing 'immutable': {cc!r}"
    assert "max-age=31536000" in cc, f"Cache-Control missing 1y max-age: {cc!r}"
    assert captured_headers["content_type"].startswith("image/"), (
        f"Content-Type is not image/*: {captured_headers['content_type']!r}"
    )
    print(f"\nCache-Control verified: {cc}")
    print(f"Content-Type: {captured_headers['content_type']}")
