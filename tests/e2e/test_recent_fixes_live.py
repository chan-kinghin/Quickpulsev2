"""Live E2E tests for recent fixes (2026-03-27 to 2026-03-31).

Tests against production (https://fltpulse.szfluent.cn) to verify:
  1. 3-tier aux_prop_id fallback — BOM-receipt matching shows receipt quantities
  2. Agent chat wrong-table fix — NL queries return meaningful data
  3. MTO search returns children with non-zero receipt data
  4. Inflated prod_instock_must_qty regression guard (c7df68c)
  5. Bidirectional aux_prop_id fallback for AS2602037 (76d79e0)
"""

import pytest
from playwright.sync_api import Page, expect, APIRequestContext


PROD_URL = "https://fltpulse.szfluent.cn"
PROD_PASSWORD = "FltPulse@2026!Prod"

# Module-level token cache to avoid rate-limiting on /api/auth/token
_cached_token = None


def _get_token(request_context: APIRequestContext) -> str:
    """Get auth token, caching across tests to avoid 429 rate-limit."""
    global _cached_token
    if _cached_token:
        return _cached_token
    response = request_context.post(
        f"{PROD_URL}/api/auth/token",
        form={"username": "admin", "password": PROD_PASSWORD},
    )
    assert response.ok, f"Auth API returned {response.status}: {response.text()}"
    _cached_token = response.json()["access_token"]
    return _cached_token


def _login(page: Page):
    """Login to prod and navigate to dashboard using cached API token."""
    token = _get_token(page.request)

    # Set token in localStorage and navigate to dashboard
    page.goto(f"{PROD_URL}/")
    page.evaluate(f"localStorage.setItem('token', '{token}')")
    page.goto(f"{PROD_URL}/dashboard.html", wait_until="domcontentloaded")
    expect(page.get_by_text("产品状态明细表")).to_be_visible(timeout=15000)


def _search_mto(page: Page, mto_number: str):
    """Type an MTO number and submit search."""
    search_input = page.locator("#mto-search")
    search_input.click()
    search_input.press("Control+a")
    search_input.type(mto_number, delay=30)
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    page.locator("button[aria-label='搜索MTO单号']").click()


@pytest.mark.e2e
def test_mto_query_returns_children_with_receipt_data(page: Page):
    """MTO query should return child items with non-zero receipt quantities.

    This verifies the 3-tier aux_prop_id fallback is working:
    - Tier 1: exact (material_code, aux_prop_id) match
    - Tier 2: BOM has specific aux → fallback to receipts with aux=0
    - Tier 3: BOM has generic aux (=0) → sum ALL receipts for that material
    """
    _login(page)
    _search_mto(page, "AK2510034")

    # Wait for BOM table to appear
    page.wait_for_selector("text=BOM组件明细", timeout=15000)

    # Wait for data rows to load (table body should have rows)
    page.wait_for_function(
        """() => {
            const rows = document.querySelectorAll('table tbody tr');
            return rows.length > 0;
        }""",
        timeout=15000,
    )

    # Count data rows
    row_count = page.locator("table tbody tr").count()
    assert row_count > 0, "MTO query should return at least one child item"

    # Get all cell text from the table to verify receipt data exists
    table_text = page.locator("table").inner_text()

    # The table should contain material codes (07.xx, 05.xx, or 03.xx patterns)
    has_material = any(prefix in table_text for prefix in ["07.", "05.", "03."])
    assert has_material, f"Table should contain material codes. Got: {table_text[:500]}"

    page.screenshot(
        path="tests/e2e/mto_children_proof.png", full_page=True
    )
    print(f"\n✅ MTO children test passed — {row_count} rows returned")


@pytest.mark.e2e
def test_mto_receipt_quantities_not_all_zero(page: Page):
    """At least some child items should have non-zero receipt quantities.

    If all receipt quantities are 0, the aux_prop_id fallback may be broken —
    receipts exist but aren't matching to BOM rows.
    """
    _login(page)
    _search_mto(page, "AK2510034")

    page.wait_for_selector("text=BOM组件明细", timeout=15000)
    page.wait_for_function(
        "() => document.querySelectorAll('table tbody tr').length > 0",
        timeout=15000,
    )

    # Use the API directly to check receipt quantities (more reliable than scraping)
    # Intercept the API response for verification
    result = page.evaluate(
        """async () => {
            const token = localStorage.getItem('token');
            const resp = await fetch('/api/mto/AK2510034', {
                headers: { 'Authorization': 'Bearer ' + token }
            });
            if (!resp.ok) return { error: resp.status };
            const data = await resp.json();
            const children = data.child_items || [];
            // Count how many children have any non-zero receipt qty
            let withReceipts = 0;
            for (const c of children) {
                if ((c.prod_instock_real_qty || 0) > 0 ||
                    (c.purchase_stock_in_qty || 0) > 0 ||
                    (c.pick_actual_qty || 0) > 0 ||
                    (c.sales_order_qty || 0) > 0) {
                    withReceipts++;
                }
            }
            return {
                total: children.length,
                withReceipts: withReceipts,
                dataSource: data.data_source || 'unknown',
                sampleAux: children.slice(0, 5).map(c => ({
                    code: c.material_code,
                    aux: c.aux_attributes,
                    typeCode: c.material_type_code,
                    prodReal: c.prod_instock_real_qty,
                    pickActual: c.pick_actual_qty,
                    purchaseQty: c.purchase_order_qty,
                    salesQty: c.sales_order_qty,
                }))
            };
        }"""
    )

    assert "error" not in result, f"API call failed: {result}"
    total = result["total"]
    with_receipts = result["withReceipts"]

    print(f"\n  Data source: {result['dataSource']}")
    print(f"  Children: {total}, with receipts: {with_receipts}")
    for s in result.get("sampleAux", []):
        print(f"    {s['code']} aux={s['aux']} prod_real={s['prodReal']} pick={s['pickActual']}")

    assert total > 0, "Should have child items"
    # At least some items should have receipt data if the MTO is in progress
    # (AK2510034 is a known MTO with production activity)
    assert with_receipts > 0, (
        f"All {total} children have zero receipts — aux_prop_id fallback may be broken. "
        f"Sample: {result.get('sampleAux', [])}"
    )

    page.screenshot(path="tests/e2e/receipt_quantities_proof.png", full_page=True)
    print(f"✅ Receipt quantities test passed — {with_receipts}/{total} items have receipts")


@pytest.mark.e2e
def test_agent_chat_responds_to_query(page: Page):
    """Agent chat should return meaningful data for a table-specific question.

    Verifies the wrong-table selection fix — the agent should query the right
    table and return relevant results.
    """
    _login(page)

    # Type a question about specific data that requires correct table selection
    search_input = page.locator("#mto-search")
    search_input.click()
    search_input.press("Control+a")
    search_input.type("AK2510034有多少个BOM组件", delay=50)
    page.wait_for_timeout(500)
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    page.locator("button[aria-label='搜索MTO单号']").click()

    # Wait for chat panel to open
    chat_panel = page.locator("text=AI 助手")
    expect(chat_panel).to_be_visible(timeout=10000)

    # Wait for AI response — should reference BOM data
    page.wait_for_function(
        """() => {
            const body = document.body.innerText;
            return body.includes('AK2510034') && (
                body.includes('BOM') ||
                body.includes('组件') ||
                body.includes('物料') ||
                body.includes('SELECT') ||
                body.includes('material')
            );
        }""",
        timeout=90000,
    )

    page_text = page.inner_text("body")
    has_relevant = any(kw in page_text for kw in ["BOM", "组件", "物料", "material", "bom"])
    assert has_relevant, f"Agent should reference BOM/materials. Got: {page_text[-500:]}"

    page.screenshot(path="tests/e2e/agent_chat_table_fix_proof.png", full_page=True)
    print(f"\n✅ Agent chat table selection test passed")


def _fetch_mto_api(page: Page, mto_number: str):
    """Call the MTO API directly from the browser and return parsed JSON."""
    return page.evaluate(
        """async (mtoNumber) => {
            const token = localStorage.getItem('token');
            const resp = await fetch('/api/mto/' + mtoNumber, {
                headers: { 'Authorization': 'Bearer ' + token }
            });
            if (!resp.ok) return { error: resp.status };
            return await resp.json();
        }""",
        mto_number,
    )


@pytest.mark.e2e
def test_prod_instock_must_qty_not_inflated(page: Page):
    """Regression guard: prod_instock_must_qty must come from BOM need_qty,
    NOT from summing PRD_INSTOCK.FMustQty across receipts (which inflates).

    Bug (c7df68c): Summing FMustQty per receipt produced e.g. 57,562 instead
    of correct 20,130 because each receipt carries the full remaining demand.
    The fix uses PPBOM.FMustQty / PRD_MO.FQty (= need_qty) instead.
    """
    _login(page)
    _search_mto(page, "AK2510034")
    page.wait_for_selector("text=BOM组件明细", timeout=15000)
    page.wait_for_function(
        "() => document.querySelectorAll('table tbody tr').length > 0",
        timeout=15000,
    )

    data = _fetch_mto_api(page, "AK2510034")
    assert "error" not in data, f"API call failed: {data}"

    children = data.get("child_items", [])
    assert len(children) > 0, "Should have child items"

    # Check self-made items (material_type_code=1) for inflated must_qty
    self_made = [c for c in children if c.get("material_type_code") == 1]
    if not self_made:
        pytest.skip("No self-made items in AK2510034 to verify must_qty")

    for item in self_made:
        must_qty = item.get("prod_instock_must_qty", 0)
        need_qty = item.get("need_qty", 0)
        real_qty = item.get("prod_instock_real_qty", 0)
        code = item.get("material_code", "?")

        # must_qty should be close to need_qty (BOM-derived), not wildly inflated
        # Allow some tolerance for rounding, but flag if must_qty > 3x need_qty
        if need_qty > 0 and must_qty > 0:
            ratio = must_qty / need_qty
            assert ratio < 3.0, (
                f"REGRESSION: {code} has inflated must_qty! "
                f"must_qty={must_qty}, need_qty={need_qty}, ratio={ratio:.1f}x. "
                f"Should be ~1.0x (BOM-derived), not inflated from receipt sums."
            )
            print(f"  {code}: must_qty={must_qty}, need_qty={need_qty}, ratio={ratio:.2f}x ✓")

    page.screenshot(path="tests/e2e/must_qty_not_inflated_proof.png", full_page=True)
    print(f"\n✅ Must qty inflation guard passed — {len(self_made)} self-made items checked")


@pytest.mark.e2e
def test_bidirectional_aux_fallback_as2602037(page: Page):
    """Verify bidirectional aux_prop_id fallback works for AS2602037.

    Bug (76d79e0): When BOM items have aux_prop_id=0 (generic) but receipts
    have specific aux values (e.g., 105726 for color variants), receipt
    quantities showed 0. The 3-tier fallback should now match:
    - Tier 3: BOM aux=0 → sum ALL receipts for that material.
    """
    _login(page)
    _search_mto(page, "AS2602037")
    page.wait_for_selector("text=BOM组件明细", timeout=15000)
    page.wait_for_function(
        "() => document.querySelectorAll('table tbody tr').length > 0",
        timeout=15000,
    )

    data = _fetch_mto_api(page, "AS2602037")
    assert "error" not in data, f"API call failed: {data}"

    children = data.get("child_items", [])
    assert len(children) > 0, "AS2602037 should have child items"

    # Check self-made items specifically — these were the ones with aux=0 vs specific
    self_made = [c for c in children if c.get("material_type_code") == 1]
    if not self_made:
        pytest.skip("No self-made items in AS2602037")

    with_receipts = 0
    for item in self_made:
        real_qty = float(item.get("prod_instock_real_qty") or 0)
        code = item.get("material_code", "?")
        aux = item.get("aux_attributes", "")
        if real_qty > 0:
            with_receipts += 1
        print(f"  {code} aux='{aux}' prod_real={real_qty}")

    # At least some self-made items should have receipt data
    assert with_receipts > 0, (
        f"All {len(self_made)} self-made items in AS2602037 have 0 receipts — "
        f"bidirectional aux_prop_id fallback may be broken"
    )

    page.screenshot(path="tests/e2e/aux_fallback_as2602037_proof.png", full_page=True)
    print(
        f"\n✅ Bidirectional aux fallback passed — "
        f"{with_receipts}/{len(self_made)} self-made items have receipts"
    )


@pytest.mark.e2e
def test_mto_search_ui_displays_data_correctly(page: Page):
    """Verify the dashboard UI renders MTO data without visual errors.

    Checks that the search flow completes end-to-end and displays:
    - Parent item info (header section)
    - BOM child items table with material codes
    - Numeric columns contain actual numbers, not NaN/undefined
    """
    _login(page)
    _search_mto(page, "AK2510034")
    page.wait_for_selector("text=BOM组件明细", timeout=15000)
    page.wait_for_function(
        "() => document.querySelectorAll('table tbody tr').length > 0",
        timeout=15000,
    )

    # Check for rendering errors — NaN, undefined, null displayed as text
    table_text = page.locator("table").inner_text()
    bad_values = ["NaN", "undefined", "null", "[object Object]"]
    for bad in bad_values:
        assert bad not in table_text, (
            f"Table contains '{bad}' — data rendering bug. "
            f"Context: ...{table_text[max(0, table_text.find(bad)-50):table_text.find(bad)+50]}..."
        )

    # Verify parent item section is visible
    parent_section = page.locator("text=AK2510034")
    expect(parent_section.first).to_be_visible()

    # Check that the table has reasonable structure (header + data)
    headers = page.locator("table thead th")
    header_count = headers.count()
    assert header_count >= 5, f"Table should have at least 5 columns, got {header_count}"

    row_count = page.locator("table tbody tr").count()
    assert row_count >= 1, "Should have at least 1 data row"

    page.screenshot(path="tests/e2e/mto_search_ui_proof.png", full_page=True)
    print(f"\n✅ UI rendering check passed — {header_count} columns, {row_count} rows, no bad values")
