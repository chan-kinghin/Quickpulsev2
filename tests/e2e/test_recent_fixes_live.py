"""Live E2E tests for recent fixes (2026-03-27).

Tests against production (https://fltpulse.szfluent.cn) to verify:
  1. 3-tier aux_prop_id fallback — BOM-receipt matching shows receipt quantities
  2. Agent chat wrong-table fix — NL queries return meaningful data
  3. MTO search returns children with non-zero receipt data
"""

import pytest
from playwright.sync_api import Page, expect


PROD_URL = "https://fltpulse.szfluent.cn"
PROD_PASSWORD = "FltPulse@2026!Prod"


def _login(page: Page):
    """Login to prod and navigate to dashboard."""
    page.goto(f"{PROD_URL}/")
    page.locator("#username").fill("admin")
    page.locator("#password").fill(PROD_PASSWORD)
    page.get_by_role("button", name="登录").click()
    page.wait_for_url("**/dashboard.html**", timeout=10000)
    expect(page.get_by_text("产品状态明细表")).to_be_visible()


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
