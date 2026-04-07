"""E2E tests for dashboard interactions: search autocomplete, error handling,
keyboard shortcuts, chat sidebar, data source badges, filter combinations,
column settings, and preferences persistence.

These tests complement the existing suite by covering UI interactions
that were previously untested.
"""

import re
from typing import Optional

import pytest
from playwright.sync_api import Page, expect


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

SAMPLE_MTO = "AK2510034"

SAMPLE_RESPONSE = {
    "parent_item": {
        "mto_number": SAMPLE_MTO,
        "customer_name": "测试客户",
        "delivery_date": "2025-02-01T00:00:00",
    },
    "child_items": [
        {
            "material_code": "07-P001",
            "material_name": "成品 A",
            "specification": "Spec A",
            "aux_attributes": "",
            "material_type": "成品",
            "material_type_code": 1,
            "is_finished_goods": True,
            "sales_order_qty": 10,
            "prod_instock_must_qty": 0,
            "purchase_order_qty": 0,
            "pick_actual_qty": 2,
            "prod_instock_real_qty": 8,
            "purchase_stock_in_qty": 0,
        },
        {
            "material_code": "05-C001",
            "material_name": "自制件 B",
            "specification": "Spec B",
            "aux_attributes": "",
            "material_type": "自制",
            "material_type_code": 1,
            "is_finished_goods": False,
            "sales_order_qty": 0,
            "prod_instock_must_qty": 5,
            "purchase_order_qty": 0,
            "pick_actual_qty": 1,
            "prod_instock_real_qty": 4,
            "purchase_stock_in_qty": 0,
        },
        {
            "material_code": "03-C002",
            "material_name": "包材 C",
            "specification": "Spec C",
            "aux_attributes": "Blue",
            "material_type": "包材",
            "material_type_code": 2,
            "is_finished_goods": False,
            "sales_order_qty": 0,
            "prod_instock_must_qty": 0,
            "purchase_order_qty": 20,
            "pick_actual_qty": 3,
            "prod_instock_real_qty": 0,
            "purchase_stock_in_qty": 18,
        },
    ],
    "data_source": "cache",
    "cache_age_seconds": 120,
}

RELATED_ORDERS_EMPTY = {"orders": {}, "documents": {}}


def _setup_authed_page(page: Page) -> None:
    """Pre-authenticate and mock auth verify."""
    page.add_init_script("localStorage.setItem('token','testtoken')")
    page.route(
        "**/api/auth/verify",
        lambda r: r.fulfill(status=200, json={"ok": True}),
    )


def _mock_chat_unavailable(page: Page) -> None:
    """Mock chat endpoints as unavailable (common default)."""
    page.route(
        "**/api/chat/status",
        lambda r: r.fulfill(
            status=200,
            json={"available": False, "model": "", "providers": [], "active": ""},
        ),
    )
    page.route(
        "**/api/agent-chat/status",
        lambda r: r.fulfill(status=200, json={"available": False}),
    )


def _mock_mto_search(page: Page, mto: str = SAMPLE_MTO, response: Optional[dict] = None) -> None:
    """Mock both MTO endpoint and related-orders.

    IMPORTANT: Register related-orders FIRST so its more-specific glob
    takes priority over the catch-all **/api/mto/<mto> pattern.
    """
    resp = response or SAMPLE_RESPONSE
    page.route(
        f"**/api/mto/{mto}/related-orders",
        lambda r: r.fulfill(status=200, json=RELATED_ORDERS_EMPTY),
    )
    page.route(f"**/api/mto/{mto}", lambda r: r.fulfill(status=200, json=resp))


def _navigate_and_search(page: Page, base_url: str, mto: str = SAMPLE_MTO) -> None:
    """Go to dashboard and perform a search."""
    page.goto(f"{base_url}/dashboard.html")
    page.locator("#mto-search").fill(mto)
    page.keyboard.press("Enter")
    expect(page.get_by_role("heading", name="BOM组件明细")).to_be_visible()


# ---------------------------------------------------------------------------
# Search autocomplete (search-as-you-type)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_search_autocomplete_shows_results(serve_frontend, base_url: str, page: Page):
    """Typing 2+ chars triggers the /api/search endpoint and shows dropdown."""
    _setup_authed_page(page)
    _mock_chat_unavailable(page)

    page.route(
        "**/api/search*",
        lambda r: r.fulfill(
            status=200,
            headers={"X-Total-Count": "2"},
            json=[
                {"mto_number": "AK2510034", "customer_name": "客户A"},
                {"mto_number": "AK2510035", "customer_name": "客户B"},
            ],
        ),
    )

    page.goto(f"{base_url}/dashboard.html")
    page.locator("#mto-search").fill("AK25")
    # Wait for debounce (300ms) + response
    page.wait_for_timeout(500)
    expect(page.get_by_text("搜索结果")).to_be_visible()
    # Use locator inside the dropdown to avoid matching sr-only help text
    dropdown = page.locator(".search-result, [class*='search-result'], div:below(#mto-search)")
    # Check the autocomplete dropdown contains our MTOs
    expect(page.locator("span:text-is('AK2510034')")).to_be_visible()
    expect(page.locator("span:text-is('AK2510035')")).to_be_visible()


@pytest.mark.e2e
def test_search_autocomplete_select_triggers_search(serve_frontend, base_url: str, page: Page):
    """Clicking a search result selects it and triggers the MTO search."""
    _setup_authed_page(page)
    _mock_chat_unavailable(page)
    _mock_mto_search(page)

    page.route(
        "**/api/search*",
        lambda r: r.fulfill(
            status=200,
            headers={"X-Total-Count": "1"},
            json=[{"mto_number": SAMPLE_MTO, "customer_name": "客户A"}],
        ),
    )

    page.goto(f"{base_url}/dashboard.html")
    page.locator("#mto-search").fill("AK25")
    page.wait_for_timeout(500)
    # Click the result item — use the span inside the dropdown
    page.locator("span:text-is('AK2510034')").click()
    expect(page.get_by_text("成功查询到 3 条BOM组件记录")).to_be_visible()


# ---------------------------------------------------------------------------
# Error states
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_mto_not_found_shows_error(serve_frontend, base_url: str, page: Page):
    """Searching for a nonexistent MTO shows an error message."""
    _setup_authed_page(page)
    _mock_chat_unavailable(page)

    page.route(
        "**/api/mto/AK9999999/related-orders",
        lambda r: r.fulfill(status=200, json=RELATED_ORDERS_EMPTY),
    )
    page.route(
        "**/api/mto/AK9999999",
        lambda r: r.fulfill(
            status=404,
            json={"detail": "MTO AK9999999 not found"},
        ),
    )

    page.goto(f"{base_url}/dashboard.html")
    page.locator("#mto-search").fill("AK9999999")
    page.keyboard.press("Enter")
    # Use exact match to avoid strict mode violation (sr-only + visible span)
    expect(page.get_by_text("MTO AK9999999 not found", exact=True)).to_be_visible()


@pytest.mark.e2e
def test_empty_search_shows_error(serve_frontend, base_url: str, page: Page):
    """Pressing Enter with empty input shows validation error."""
    _setup_authed_page(page)
    _mock_chat_unavailable(page)

    page.goto(f"{base_url}/dashboard.html")
    page.locator("#mto-search").fill("")
    page.keyboard.press("Enter")
    # exact=True to distinguish from "请输入MTO单号进行查询" placeholder text
    expect(page.get_by_text("请输入MTO单号", exact=True)).to_be_visible()


@pytest.mark.e2e
def test_network_error_shows_error(serve_frontend, base_url: str, page: Page):
    """Network failure during MTO search shows error message."""
    _setup_authed_page(page)
    _mock_chat_unavailable(page)

    page.route(
        "**/api/mto/AK1111111",
        lambda r: r.abort("connectionrefused"),
    )

    page.goto(f"{base_url}/dashboard.html")
    page.locator("#mto-search").fill("AK1111111")
    page.keyboard.press("Enter")
    # The error span (x-text="error") should become visible with some message
    error_span = page.locator("span[x-text='error']")
    expect(error_span).not_to_be_empty()
    page.wait_for_timeout(500)
    error_text = error_span.text_content()
    assert error_text and len(error_text) > 0, "Expected an error message to be displayed"


# ---------------------------------------------------------------------------
# Data source badge (cache vs live)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_cache_data_source_shows_badge(serve_frontend, base_url: str, page: Page):
    """When data comes from cache, a cache badge/indicator is shown."""
    _setup_authed_page(page)
    _mock_chat_unavailable(page)
    _mock_mto_search(page, response={
        **SAMPLE_RESPONSE,
        "data_source": "cache",
        "cache_age_seconds": 300,
    })

    _navigate_and_search(page, base_url)
    # The data source indicator should mention "缓存" or "cache"
    expect(page.get_by_text("缓存").first).to_be_visible()


@pytest.mark.e2e
def test_live_data_source_shows_badge(serve_frontend, base_url: str, page: Page):
    """When data comes from live API, a live badge is shown."""
    _setup_authed_page(page)
    _mock_chat_unavailable(page)
    _mock_mto_search(page, response={
        **SAMPLE_RESPONSE,
        "data_source": "live",
        "cache_age_seconds": None,
    })

    _navigate_and_search(page, base_url)
    expect(page.get_by_text("实时").first).to_be_visible()


# ---------------------------------------------------------------------------
# Keyboard shortcuts
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_slash_key_focuses_search(serve_frontend, base_url: str, page: Page):
    """Pressing '/' when not in an input focuses the MTO search box."""
    _setup_authed_page(page)
    _mock_chat_unavailable(page)

    page.goto(f"{base_url}/dashboard.html")
    # Click body so focus is not in an input
    page.locator("body").click()
    page.keyboard.press("/")
    # The search input should now be focused
    focused_id = page.evaluate("document.activeElement?.id")
    assert focused_id == "mto-search", f"Expected mto-search focused, got {focused_id}"


@pytest.mark.e2e
def test_escape_exits_fullscreen(serve_frontend, base_url: str, page: Page):
    """Pressing Escape while in fullscreen exits fullscreen mode."""
    _setup_authed_page(page)
    _mock_chat_unavailable(page)
    _mock_mto_search(page)

    _navigate_and_search(page, base_url)

    # Enter fullscreen
    page.get_by_role("button", name="全屏").click()
    expect(page.get_by_role("button", name="退出全屏")).to_be_visible()

    # Press Escape
    page.keyboard.press("Escape")
    expect(page.get_by_role("button", name="全屏")).to_be_visible()


# ---------------------------------------------------------------------------
# Material type filter combinations
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_multiple_filters_combined(serve_frontend, base_url: str, page: Page):
    """Toggling off multiple material type filters hides rows correctly."""
    _setup_authed_page(page)
    _mock_chat_unavailable(page)
    _mock_mto_search(page)

    _navigate_and_search(page, base_url)

    # Wait for rows to render
    page.wait_for_timeout(300)
    initial_count = page.locator("tbody tr").count()
    assert initial_count == 3, f"Expected 3 rows, got {initial_count}"

    # Toggle off 成品 — should hide 1 row (07-P001)
    page.get_by_role("button", name="成品").click()
    page.wait_for_timeout(300)
    visible_after_1 = page.locator("tbody tr").count()
    assert visible_after_1 < initial_count

    # Toggle off 自制 — should hide another row (05-C001)
    page.get_by_role("button", name="自制").click()
    page.wait_for_timeout(300)
    visible_after_2 = page.locator("tbody tr").count()
    assert visible_after_2 < visible_after_1

    # Re-enable 成品
    page.get_by_role("button", name="成品").click()
    page.wait_for_timeout(300)
    visible_after_re = page.locator("tbody tr").count()
    assert visible_after_re > visible_after_2


# ---------------------------------------------------------------------------
# Chat sidebar
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_chat_sidebar_opens_and_closes(serve_frontend, base_url: str, page: Page):
    """Chat sidebar can be toggled open and closed via the FAB button."""
    _setup_authed_page(page)
    page.route(
        "**/api/chat/status",
        lambda r: r.fulfill(
            status=200,
            json={
                "available": True,
                "model": "deepseek-chat",
                "providers": [{"name": "deepseek", "label": "DeepSeek", "model": "deepseek-chat"}],
                "active": "deepseek",
            },
        ),
    )
    page.route(
        "**/api/agent-chat/status",
        lambda r: r.fulfill(status=200, json={"available": True}),
    )

    page.goto(f"{base_url}/dashboard.html")
    page.wait_for_timeout(500)

    # The sidebar is rendered (via x-if when chatAvailable) but should be
    # off-screen (chat-sidebar-closed uses translateX(100%))
    sidebar = page.locator(".chat-sidebar")
    expect(sidebar).to_have_class(re.compile("chat-sidebar-closed"))

    # Click FAB chat button (the circular button with chat icon)
    page.locator("button[title='AI 助手']").click()
    expect(sidebar).to_have_class(re.compile("chat-sidebar-open"))

    # Close via Escape — the Escape handler sets chatOpen = false
    page.keyboard.press("Escape")
    expect(sidebar).to_have_class(re.compile("chat-sidebar-closed"))


@pytest.mark.e2e
def test_chat_mode_switch(serve_frontend, base_url: str, page: Page):
    """User can switch between simple and agent chat modes."""
    _setup_authed_page(page)
    page.route(
        "**/api/chat/status",
        lambda r: r.fulfill(
            status=200,
            json={
                "available": True,
                "model": "deepseek-chat",
                "providers": [{"name": "deepseek", "label": "DeepSeek", "model": "deepseek-chat"}],
                "active": "deepseek",
            },
        ),
    )
    page.route(
        "**/api/agent-chat/status",
        lambda r: r.fulfill(status=200, json={"available": True}),
    )

    page.goto(f"{base_url}/dashboard.html")
    page.wait_for_timeout(500)

    # Open chat via FAB
    page.locator("button[title='AI 助手']").click()
    sidebar = page.locator(".chat-sidebar")
    expect(sidebar).to_have_class(re.compile("chat-sidebar-open"))

    # The mode toggle has "简单" and "智能" buttons
    simple_btn = sidebar.locator("button:has-text('简单')")
    agent_btn = sidebar.locator("button:has-text('智能')")

    # Initially simple mode is active (has emerald bg)
    expect(simple_btn).to_have_class(re.compile("bg-emerald"))

    # Switch to agent mode
    agent_btn.click()
    page.wait_for_timeout(200)
    expect(agent_btn).to_have_class(re.compile("bg-emerald"))


# ---------------------------------------------------------------------------
# Column width reset
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_column_width_reset(serve_frontend, base_url: str, page: Page):
    """The '重置列宽' button exists in column settings and can be clicked."""
    _setup_authed_page(page)
    _mock_chat_unavailable(page)
    _mock_mto_search(page)

    _navigate_and_search(page, base_url)

    # Open column settings
    page.locator("button[aria-label='Column settings']").click()
    reset_btn = page.get_by_text("重置列宽")
    expect(reset_btn).to_be_visible()
    # Click it — should close settings
    reset_btn.click()


# ---------------------------------------------------------------------------
# Preferences persistence (localStorage)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_preferences_persist_across_reload(serve_frontend, base_url: str, page: Page):
    """Column visibility preferences survive a page reload."""
    _setup_authed_page(page)
    _mock_chat_unavailable(page)
    _mock_mto_search(page)

    _navigate_and_search(page, base_url)

    # Hide a column
    page.locator("button[aria-label='Column settings']").click()
    page.locator(".column-settings .column-settings-item:has-text('辅助属性') input").click()
    page.keyboard.press("Escape")
    expect(page.get_by_role("columnheader", name="辅助属性")).not_to_be_visible()

    # Reload and re-search
    page.reload()
    page.locator("#mto-search").fill(SAMPLE_MTO)
    page.keyboard.press("Enter")
    expect(page.get_by_role("heading", name="BOM组件明细")).to_be_visible()

    # Column should still be hidden
    expect(page.get_by_role("columnheader", name="辅助属性")).not_to_be_visible()


# ---------------------------------------------------------------------------
# Natural language query routing to chat
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_nl_query_opens_chat(serve_frontend, base_url: str, page: Page):
    """Typing a natural language query (not MTO number) into search
    should open the chat sidebar instead of doing an MTO search."""
    _setup_authed_page(page)
    page.route(
        "**/api/chat/status",
        lambda r: r.fulfill(
            status=200,
            json={
                "available": True,
                "model": "deepseek-chat",
                "providers": [{"name": "deepseek", "label": "DeepSeek", "model": "deepseek-chat"}],
                "active": "deepseek",
            },
        ),
    )
    page.route(
        "**/api/agent-chat/status",
        lambda r: r.fulfill(status=200, json={"available": True}),
    )
    # Mock the agent-chat stream to return quickly
    page.route(
        "**/api/agent-chat/stream",
        lambda r: r.fulfill(
            status=200,
            content_type="text/event-stream",
            body="data: {\"type\":\"token\",\"content\":\"Hello\"}\n\ndata: {\"type\":\"done\"}\n\n",
        ),
    )

    page.goto(f"{base_url}/dashboard.html")
    page.wait_for_timeout(500)
    page.locator("#mto-search").fill("有多少订单")
    page.keyboard.press("Enter")

    # Chat sidebar should open (switch to open class)
    sidebar = page.locator(".chat-sidebar")
    expect(sidebar).to_have_class(re.compile("chat-sidebar-open"))


# ---------------------------------------------------------------------------
# Loading state
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_loading_state_during_search(serve_frontend, base_url: str, page: Page):
    """A loading indicator appears while waiting for MTO response."""
    _setup_authed_page(page)
    _mock_chat_unavailable(page)

    # Use a list to hold the route so we can fulfill it later
    pending = []

    def capture_mto(route):
        pending.append(route)

    page.route(
        f"**/api/mto/{SAMPLE_MTO}/related-orders",
        lambda r: r.fulfill(status=200, json=RELATED_ORDERS_EMPTY),
    )
    page.route(f"**/api/mto/{SAMPLE_MTO}", capture_mto)

    page.goto(f"{base_url}/dashboard.html")
    page.locator("#mto-search").fill(SAMPLE_MTO)
    page.keyboard.press("Enter")

    # Wait a moment for the request to be captured and loading state to activate
    page.wait_for_timeout(300)

    # Search input should be disabled during loading
    is_disabled = page.locator("#mto-search").is_disabled()
    assert is_disabled, "Expected search input to be disabled while loading"

    # Now fulfill the pending request
    assert len(pending) > 0, "MTO request was not captured"
    pending[0].fulfill(status=200, json=SAMPLE_RESPONSE)

    # Eventually results appear
    expect(page.get_by_text("成功查询到 3 条BOM组件记录")).to_be_visible(timeout=10000)
    expect(page.locator("#mto-search")).to_be_enabled()


# ---------------------------------------------------------------------------
# URL updates after search
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_url_updates_after_search(serve_frontend, base_url: str, page: Page):
    """After a successful search, the URL should contain ?mto=<number>."""
    _setup_authed_page(page)
    _mock_chat_unavailable(page)
    _mock_mto_search(page)

    page.goto(f"{base_url}/dashboard.html")
    page.locator("#mto-search").fill(SAMPLE_MTO)
    page.keyboard.press("Enter")
    expect(page.get_by_text("成功查询到 3 条BOM组件记录")).to_be_visible()

    # Check URL contains the MTO param
    assert f"mto={SAMPLE_MTO}" in page.url


# ---------------------------------------------------------------------------
# User menu navigation
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_user_menu_has_navigation_links(serve_frontend, base_url: str, page: Page):
    """User menu contains links to sync and admin pages."""
    _setup_authed_page(page)
    _mock_chat_unavailable(page)

    page.goto(f"{base_url}/dashboard.html")
    page.get_by_role("button", name="用户").click()

    expect(page.get_by_text("同步管理")).to_be_visible()
    expect(page.get_by_text("使用分析")).to_be_visible()
    expect(page.get_by_text("退出登录")).to_be_visible()


# ---------------------------------------------------------------------------
# Sort toggle cycles through asc / desc / none
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_sort_toggle_cycles(serve_frontend, base_url: str, page: Page):
    """Clicking a sortable column header cycles: asc → desc → none."""
    _setup_authed_page(page)
    _mock_chat_unavailable(page)
    _mock_mto_search(page)

    _navigate_and_search(page, base_url)

    # Wait for rows to render
    page.wait_for_timeout(500)
    assert page.locator("tbody tr").count() > 0, "No rows rendered"

    # Use JS to trigger sort directly — column headers can be obscured
    # by sticky positioning in headless mode
    def first_code():
        return page.evaluate(
            "() => { const row = document.querySelector('tbody tr');"
            " if(!row) return ''; const tds = Array.from(row.querySelectorAll('td'));"
            " const m = tds.map(td => td.innerText.trim()).find(x => /^\\d{2}-/.test(x));"
            " return m || ''; }"
        )

    # Trigger sort via JS (avoids click interception by sticky elements)
    page.evaluate("() => document.querySelector('th[role=button]').click()")
    page.wait_for_timeout(300)
    code_first = first_code()

    page.evaluate("() => document.querySelector('th[role=button]').click()")
    page.wait_for_timeout(300)
    code_second = first_code()

    # The two sort orders should produce different first rows
    assert code_first != code_second, (
        f"Sort toggle had no effect: both clicks show {code_first}"
    )


# ---------------------------------------------------------------------------
# Accessibility: skip link
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_skip_link_present_in_dom(serve_frontend, base_url: str, page: Page):
    """The page contains a skip-to-content link for accessibility."""
    _setup_authed_page(page)
    _mock_chat_unavailable(page)

    page.goto(f"{base_url}/dashboard.html")
    skip = page.locator("a[href='#main-content']")
    expect(skip).to_have_count(1)
    # Verify it has the correct text
    expect(skip).to_have_text("跳转到主要内容")


# ---------------------------------------------------------------------------
# Login page basics
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_login_page_renders(serve_frontend, base_url: str, page: Page):
    """The login page renders with username and password fields."""
    page.goto(f"{base_url}/")
    expect(page.locator("#username")).to_be_visible()
    expect(page.locator("#password")).to_be_visible()
    expect(page.get_by_role("button", name="登录")).to_be_visible()


# ---------------------------------------------------------------------------
# Filtered badge text
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_filtered_badge_shows_count(serve_frontend, base_url: str, page: Page):
    """When a filter is active, the '已筛选' badge shows a count."""
    _setup_authed_page(page)
    _mock_chat_unavailable(page)
    _mock_mto_search(page)

    _navigate_and_search(page, base_url)

    # Toggle off 包材 filter
    page.get_by_role("button", name="包材").click()
    badge = page.get_by_text("已筛选").first
    expect(badge).to_be_visible()
