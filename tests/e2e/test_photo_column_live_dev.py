"""Live-dev verification of MTO-level photo entry point + lightbox modal.

Phase A redesign (2026-05-11): photos are PRD_MO-level — every BOM row in a
single-parent MTO carries the same set. Showing a per-row 📷 column repeated
the same content N times, so the column was removed and a single 📷 button
was added to the MTO/parent info bar. Inline panel + modal click-through
flow is unchanged.

Assumes uvicorn is already running on $E2E_BASE_URL (defaults to
http://localhost:8000). Skip silently if the server is not up.

Run with:
    E2E_BASE_URL=http://127.0.0.1:8005 pytest \
        tests/e2e/test_photo_column_live_dev.py --run-e2e -v
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


def _open_results(page: Page) -> None:
    page.locator("#mto-search").fill(MTO_NUMBER)
    page.keyboard.press("Enter")
    expect(page.get_by_role("heading", name="BOM组件明细")).to_be_visible(timeout=30_000)


def test_no_per_row_photo_column_or_badge(page: Page):
    """Regression guard: 照片 column is gone, no 📷 button in tbody."""
    _login(page)
    _open_results(page)

    # No 照片 column header
    column_present = page.evaluate("""
        () => [...document.querySelectorAll('thead th')]
            .some(th => th.innerText.trim() === '照片')
    """)
    assert not column_present, "照片 column should have been removed from BOM thead"

    # No 📷 button on any tbody row
    badge_count = page.evaluate("""
        () => [...document.querySelectorAll('tbody tr button')]
            .filter(b => /📷/.test(b.innerText)).length
    """)
    assert badge_count == 0, (
        f"Expected zero per-row 📷 badges; found {badge_count}. "
        "Photos belong on the parent info bar, not per row."
    )


def test_parent_photo_button_visible_and_labeled(page: Page):
    """The single MTO-level photo button shows with a count when photos exist."""
    _login(page)
    _open_results(page)

    btn = page.locator('[data-testid="parent-photo-button"]')
    expect(btn).to_be_visible(timeout=10_000)
    text = btn.inner_text().strip()
    assert "📷" in text, f"button should carry the 📷 glyph; got {text!r}"
    # Expect "照片 ×N" with N being a positive integer (DS264102S has multiple photos)
    m = re.search(r"照片\s*×(\d+)", text)
    assert m, f"button label should match '照片 ×N'; got {text!r}"
    count = int(m.group(1))
    assert count > 0, f"expected photo count > 0; got {count}"

    page.screenshot(
        path=str(_SCREENSHOT_DIR / "photo_column_dev_live_proof.png"),
        full_page=True,
    )
    print(f"\nParent photo button label: {text!r} (count={count})")


def test_clicking_parent_button_opens_inline_panel_and_loads_image(page: Page):
    """Click parent 📷 button → inline photo panel appears, main image loads."""
    _login(page)
    _open_results(page)

    page.locator('[data-testid="parent-photo-button"]').click()

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
    _open_results(page)

    page.locator('[data-testid="parent-photo-button"]').click()

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
    _open_results(page)

    page.locator('[data-testid="parent-photo-button"]').click()
    inline_img = page.locator('[data-testid="photo-inline-main-img"]')
    expect(inline_img).to_be_visible(timeout=10_000)

    inline_img.click()

    # Modal overlay has class fixed inset-0 z-50.
    modal = page.locator("div.fixed.inset-0.z-50").first
    expect(modal).to_be_visible(timeout=5_000)

    # Escape must close the modal (critical user-facing contract). Whether the
    # inline panel also closes is implementation-defined — there are two Escape
    # handlers (JS document-level + Alpine window-level) and both may fire,
    # which is acceptable UX (one keypress dismisses both).
    page.keyboard.press("Escape")
    expect(modal).not_to_be_visible(timeout=5_000)
    print("\nLightbox flow verified: inline → modal → Escape closes modal")


def test_photo_response_has_immutable_cache_header(page: Page):
    """Watch the network — /api/photo response must declare immutable cache."""
    _login(page)
    _open_results(page)

    captured_headers: dict = {}

    def on_response(resp):
        if "/api/photo/" in resp.url and resp.status == 200:
            captured_headers["url"] = resp.url
            captured_headers["cache_control"] = resp.headers.get("cache-control", "")
            captured_headers["content_type"] = resp.headers.get("content-type", "")

    page.on("response", on_response)

    page.locator('[data-testid="parent-photo-button"]').click()
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
