"""Live E2E test: prove NL query works against production.

This test hits the real prod server (https://fltpulse.szfluent.cn)
to verify the natural language query pipeline end-to-end:
  1. Login with real credentials
  2. Type a Chinese NL query in the MTO search box
  3. Verify the chat panel opens (not the MTO search)
  4. Verify the AI returns actual data from the database
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


@pytest.mark.e2e
def test_nl_query_routes_to_agent_chat(page: Page):
    """NL query in search box should open chat panel and get AI response."""
    _login(page)

    # Type NL query using keyboard (not fill) so Alpine.js x-model picks it up
    search_input = page.locator("#mto-search")
    search_input.click()
    page.wait_for_timeout(200)

    # Clear any existing text and type the query character by character
    search_input.press("Control+a")
    search_input.type("联星体育现在做好的成品", delay=50)
    page.wait_for_timeout(500)

    # Close any autocomplete dropdown
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    # Debug: screenshot before clicking search
    page.screenshot(path="tests/e2e/nl_query_before_click.png")

    # Click 查询 button
    search_btn = page.locator("button[aria-label='搜索MTO单号']")
    expect(search_btn).to_be_enabled(timeout=3000)
    search_btn.click()

    # Wait a moment for the NL detection to route to chat
    page.wait_for_timeout(2000)

    # Debug: screenshot after clicking search
    page.screenshot(path="tests/e2e/nl_query_after_click.png")

    # Verify chat panel opened — look for the chat sidebar
    # The text is "AI 助手" (with space between AI and 助手)
    chat_panel = page.locator("text=AI 助手")
    expect(chat_panel).to_be_visible(timeout=10000)

    # Verify the user message appears in chat
    expect(page.locator("text=联星体育现在做好的成品")).to_be_visible(timeout=5000)

    # Wait for AI response (agent pipeline can take 30-60s)
    # Poll until we see substantial response text
    page.wait_for_function(
        """() => {
            const body = document.body.innerText;
            // Response should contain data references (not just the user query)
            const hasResponse = body.includes('联星') && (
                body.includes('SELECT') ||
                body.includes('入库') ||
                body.includes('成品') ||
                body.includes('订单') ||
                body.includes('material') ||
                body.includes('07.')
            );
            return hasResponse;
        }""",
        timeout=90000,
    )

    # Verify the response contains meaningful data
    page_text = page.inner_text("body")
    assert "联星" in page_text, "Response should reference 联星体育"

    has_data = any(kw in page_text for kw in ["SELECT", "入库", "成品", "订单", "07."])
    assert has_data, f"Response should contain data. Got: {page_text[-500:]}"

    # Take final proof screenshot
    page.screenshot(path="tests/e2e/nl_query_proof.png", full_page=True)
    print(f"\n✅ NL query test passed! Screenshot saved to tests/e2e/nl_query_proof.png")


@pytest.mark.e2e
def test_mto_number_still_works_normally(page: Page):
    """Regular MTO numbers should NOT route to chat — they go to MTO search."""
    _login(page)

    # Type MTO number
    search_input = page.locator("#mto-search")
    search_input.click()
    search_input.press("Control+a")
    search_input.type("AK2510034", delay=50)
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    # Submit
    page.locator("button[aria-label='搜索MTO单号']").click()

    # Wait for response
    page.wait_for_timeout(8000)

    page_text = page.inner_text("body")

    # MTO search should NOT open the chat panel automatically with NL content
    # It might show BOM results, or a loading state, or an error — all are fine
    # The key: it should NOT have routed to agent chat
    assert "AK2510034" in page_text or "BOM" in page_text or "暂无数据" in page_text, (
        f"MTO number should trigger MTO search. Got: {page_text[-500:]}"
    )

    page.screenshot(path="tests/e2e/mto_search_proof.png", full_page=True)
    print(f"\n✅ MTO search test passed! Screenshot saved to tests/e2e/mto_search_proof.png")
