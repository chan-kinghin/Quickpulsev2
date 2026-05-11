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
AUTH_USERNAME = os.environ.get("E2E_AUTH_USERNAME", "admin")
AUTH_PASSWORD = os.environ.get("E2E_AUTH_PASSWORD", "quickpulse")
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
    page.locator("#username").fill(AUTH_USERNAME)
    page.locator("#password").fill(AUTH_PASSWORD)
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


def test_clicking_badge_opens_inline_panel_and_loads_image(page: Page):
    """Click the first 📷 badge → inline photo panel below the table appears,
    main image loads via /api/photo/{id}."""
    _login(page)
    page.locator("#mto-search").fill(MTO_NUMBER)
    page.keyboard.press("Enter")
    expect(page.get_by_role("heading", name="BOM组件明细")).to_be_visible(timeout=30_000)

    badge = page.locator("tbody tr button").filter(has_text="📷").first
    expect(badge).to_be_visible(timeout=10_000)
    badge.click()

    panel = page.locator('[data-testid="photo-inline-panel"]')
    expect(panel).to_be_visible(timeout=10_000)

    main_img = page.locator('[data-testid="photo-inline-main-img"]')
    expect(main_img).to_be_visible(timeout=10_000)
    src = main_img.get_attribute("src")
    assert src and re.match(r"^/api/photo/[a-f0-9]{32}$", src), (
        f"Inline main image src is not a clean /api/photo/{{guid}} URL: {src!r}"
    )
    page.wait_for_function(
        """() => {
            const img = document.querySelector('[data-testid="photo-inline-main-img"]');
            return img && img.complete && img.naturalWidth > 0;
        }""",
        timeout=15_000,
    )

    page.wait_for_timeout(300)
    page.screenshot(
        path=str(_SCREENSHOT_DIR / "photo_inline_panel_proof.png"),
        full_page=True,
    )
    print(f"\nInline panel main image loaded: {src}")


def test_inline_panel_keyboard_navigation_and_close(page: Page):
    """ArrowRight advances, ArrowLeft goes back, Escape closes the inline panel."""
    _login(page)
    page.locator("#mto-search").fill(MTO_NUMBER)
    page.keyboard.press("Enter")
    expect(page.get_by_role("heading", name="BOM组件明细")).to_be_visible(timeout=30_000)

    page.locator("tbody tr button").filter(has_text="📷").first.click()

    main_img = page.locator('[data-testid="photo-inline-main-img"]')
    expect(main_img).to_be_visible(timeout=10_000)
    first_src = main_img.get_attribute("src")

    page.keyboard.press("ArrowRight")
    page.wait_for_function(
        f"""() => {{
            const img = document.querySelector('[data-testid="photo-inline-main-img"]');
            return img && img.src && !img.src.endsWith('{first_src.split('/')[-1]}');
        }}""",
        timeout=5_000,
    )
    assert main_img.get_attribute("src") != first_src, "ArrowRight did not advance"

    page.keyboard.press("ArrowLeft")
    page.wait_for_function(
        f"""() => {{
            const img = document.querySelector('[data-testid="photo-inline-main-img"]');
            return img && img.src.endsWith('{first_src.split('/')[-1]}');
        }}""",
        timeout=5_000,
    )

    page.keyboard.press("Escape")
    expect(page.locator('[data-testid="photo-inline-panel"]')).not_to_be_visible(timeout=5_000)
    print("\nKeyboard nav verified: ArrowRight → ArrowLeft → Escape all worked")


def test_clicking_inline_main_image_opens_lightbox(page: Page):
    """Inline main image is click-through to the full-screen modal."""
    _login(page)
    page.locator("#mto-search").fill(MTO_NUMBER)
    page.keyboard.press("Enter")
    expect(page.get_by_role("heading", name="BOM组件明细")).to_be_visible(timeout=30_000)

    page.locator("tbody tr button").filter(has_text="📷").first.click()
    inline_img = page.locator('[data-testid="photo-inline-main-img"]')
    expect(inline_img).to_be_visible(timeout=10_000)

    inline_img.click()

    # Modal overlay has class fixed inset-0 z-50.
    modal = page.locator("div.fixed.inset-0.z-50").first
    expect(modal).to_be_visible(timeout=5_000)

    # Closing modal with Escape should NOT close the inline panel (since
    # the @keydown handler closes modal first when both are open).
    page.keyboard.press("Escape")
    expect(modal).not_to_be_visible(timeout=5_000)
    expect(page.locator('[data-testid="photo-inline-panel"]')).to_be_visible()
    print("\nLightbox flow verified: inline → modal → Escape returns to inline")


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

    page.locator("tbody tr button").filter(has_text="📷").first.click()
    expect(page.locator('[data-testid="photo-inline-main-img"]')).to_be_visible(timeout=10_000)

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
