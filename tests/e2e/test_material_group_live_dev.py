"""Live-dev verification of the 物料分组 column (no API mocks).

Assumes uvicorn is already running on http://localhost:8000 and that a sync
has populated cached_production_bom.material_group_name. Goes through the real
login form, fires a real MTO query, and asserts that at least some children
display non-empty Chinese group names.

Run with:
    pytest tests/e2e/test_material_group_live_dev.py --run-e2e -v

Skip silently if the dev server is not up (so this test is safe in CI without
a running backend).
"""

from pathlib import Path

import pytest
import requests
from playwright.sync_api import Page, expect


BASE_URL = "http://localhost:8000"
# Pick a recent MTO that's within the last 30-day sync window so the cache
# carries material_group_name. AK2510034 (the long-standing test MTO) is from
# Feb so its cached rows pre-date column 011 and wouldn't have group names.
MTO_NUMBER = "AS2603016"
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
        reason=f"Live dev server not running at {BASE_URL}",
    ),
]


def _login(page: Page) -> None:
    """Submit the real login form with default admin creds."""
    page.goto(f"{BASE_URL}/")
    page.locator("#username").fill("admin")
    page.locator("#password").fill("quickpulse")
    with page.expect_navigation(url=f"{BASE_URL}/dashboard.html"):
        page.get_by_role("button", name="登录").click()


def test_dev_live_query_populates_material_group_column(page: Page):
    """End-to-end: real login → live MTO query → 物料分组 column shows real data."""
    _login(page)

    # Force live path so we don't depend on sync having completed.
    # The frontend doesn't expose `use_cache` toggle in the URL by default —
    # the cache is consulted first, then the live path is used as fallback.
    # For first-cut verification, that's fine: a populated cache OR a live hit
    # both surface group names.
    page.locator("#mto-search").fill(MTO_NUMBER)
    page.keyboard.press("Enter")
    expect(page.get_by_role("heading", name="BOM组件明细")).to_be_visible(timeout=30_000)

    # Pull the (material_code, material_group_name) pairs out of the rendered DOM.
    rows = page.evaluate("""
        () => {
            const allTh = [...document.querySelectorAll('thead th')];
            const idx = allTh.findIndex(th => th.innerText.includes('物料分组'));
            if (idx < 0) return { idx: -1, rows: [] };
            const tbodyRows = [...document.querySelectorAll('tbody tr')];
            const rows = tbodyRows.map(tr => {
                const code = tr.querySelector('td:nth-child(2)')?.innerText?.trim() || '';
                const group = tr.querySelectorAll('td')[idx]?.innerText?.trim() ?? '';
                return { code, group };
            });
            return { idx, rows };
        }
    """)

    assert rows["idx"] >= 0, "物料分组 column header must be present"
    assert len(rows["rows"]) > 0, "expected at least one BOM child row"

    non_empty = [r for r in rows["rows"] if r["group"] and r["group"] != "-"]
    assert non_empty, (
        f"No rows had a non-empty 物料分组. Sample: {rows['rows'][:5]}. "
        "Either live API didn't return groups (check FMaterialId.FMaterialGroup) "
        "or cache is stale and live fallback also failed."
    )

    # Spot-check: at least one Chinese character in a group name (sanity).
    has_chinese = any(
        any("一" <= ch <= "鿿" for ch in r["group"]) for r in non_empty
    )
    assert has_chinese, f"No Chinese in groups: {non_empty[:5]}"

    # Surface a few examples in the test log for visual confirmation.
    print(f"\n物料分组 column populated on {len(non_empty)}/{len(rows['rows'])} rows.")
    for r in non_empty[:8]:
        print(f"  {r['code']:24s} → {r['group']}")

    page.screenshot(
        path=str(_SCREENSHOT_DIR / "material_group_dev_live_proof.png"),
        full_page=True,
    )


def test_dev_live_data_source_matches_screenshot_expectations(page: Page):
    """Sanity check: the data-source badge says either 实时 or 缓存."""
    _login(page)
    page.locator("#mto-search").fill(MTO_NUMBER)
    page.keyboard.press("Enter")
    expect(page.get_by_role("heading", name="BOM组件明细")).to_be_visible(timeout=30_000)

    # Either "实时" (live) or "缓存" (cache) should appear in the data-source badge
    badge_text = page.evaluate("""
        () => {
            const el = [...document.querySelectorAll('*')]
                .find(n => /数据/.test(n.innerText) && /(实时|缓存)/.test(n.innerText));
            return el ? el.innerText : '';
        }
    """)
    assert any(s in badge_text for s in ("实时", "缓存")), (
        f"Data source badge missing or unexpected: {badge_text!r}"
    )
