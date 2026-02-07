import urllib.parse

import pytest
from playwright.sync_api import Page, expect


def _route_dynamic_mto(page: Page):
    def handler(route):
        url = route.request.url
        mto = url.split("/api/mto/")[-1]
        # Produce differing child counts based on last digit
        count = 1 if mto.endswith("1") else 2
        items = [
            {"material_code": "07-P001", "material_name": "成品 A", "material_type": "成品", "sales_order_qty": 10},
        ]
        if count == 2:
            items.append({"material_code": "05-C001", "material_name": "自制件 B", "material_type": "自制", "prod_instock_must_qty": 5})
        route.fulfill(
            status=200,
            json={
                "parent_item": {"mto_number": mto},
                "child_items": items,
                "data_source": "live",
            },
        )

    page.route("**/api/mto/**", handler)
    page.route("**/api/mto/**/related-orders", lambda r: r.fulfill(status=200, json={"orders": {}, "documents": {}}))


@pytest.mark.e2e
def test_search_history_interactions(serve_frontend, base_url: str, page: Page):
    page.add_init_script("localStorage.setItem('token','testtoken')")
    page.route("**/api/auth/verify", lambda r: r.fulfill(status=200, json={"ok": True}))
    _route_dynamic_mto(page)

    page.goto(f"{base_url}/dashboard.html")

    # First search → 1 item
    page.locator("#mto-search").fill("AK0000001")
    page.keyboard.press("Enter")
    expect(page.get_by_text("成功查询到 1 条BOM组件记录")).to_be_visible()

    # Second search → 2 items
    page.locator("#mto-search").fill("AK0000002")
    page.keyboard.press("Enter")
    expect(page.get_by_text("成功查询到 2 条BOM组件记录")).to_be_visible()

    # Focus input to show history and verify both entries
    page.locator("#mto-search").focus()
    dropdown = page.locator(".search-history")
    expect(dropdown).to_be_visible()
    expect(dropdown.get_by_text("AK0000002", exact=True)).to_be_visible()
    expect(dropdown.get_by_text("AK0000001", exact=True)).to_be_visible()

    # Pick older entry from history and verify result (mousedown is used in the component)
    page.locator(".search-history-item:has-text('AK0000001')").dispatch_event("mousedown")
    expect(page.get_by_text("成功查询到 1 条BOM组件记录")).to_be_visible()

    # Clear history and ensure dropdown no longer appears on re-focus
    page.locator("#mto-search").focus()
    dropdown = page.locator(".search-history")
    expect(dropdown).to_be_visible()
    dropdown.get_by_role("button", name="清除").click()
    # blur + refocus to re-evaluate
    page.keyboard.press("Escape")
    page.locator("#mto-search").focus()
    expect(page.get_by_text("最近搜索")).not_to_be_visible()


@pytest.mark.e2e
def test_sorting_by_material_code(serve_frontend, base_url: str, page: Page):
    page.add_init_script("localStorage.setItem('token','testtoken')")
    page.route("**/api/auth/verify", lambda r: r.fulfill(status=200, json={"ok": True}))
    # Provide 3 rows for sort checks
    page.route(
        "**/api/mto/AKSORT",
        lambda r: r.fulfill(
            status=200,
            json={
                "parent_item": {"mto_number": "AKSORT"},
                "child_items": [
                    {"material_code": "07-P001", "material_name": "A", "material_type": "成品"},
                    {"material_code": "03-C002", "material_name": "B", "material_type": "包材"},
                    {"material_code": "05-C001", "material_name": "C", "material_type": "自制"},
                ],
                "data_source": "live",
            },
        ),
    )
    page.route("**/api/mto/AKSORT/related-orders", lambda r: r.fulfill(status=200, json={"orders": {}, "documents": {}}))

    page.goto(f"{base_url}/dashboard.html")
    page.locator("#mto-search").fill("AKSORT")
    page.keyboard.press("Enter")
    # Wait for table and click "物料编码" header to sort asc
    expect(page.locator("tbody tr").first).to_be_visible()
    page.get_by_role("columnheader", name="物料编码").click()
    code = page.evaluate(
        "() => { const row = document.querySelector('tbody tr'); if(!row) return ''; const tds = Array.from(row.querySelectorAll('td')); const m = tds.map(td => td.innerText.trim()).find(x => /^\\d{2}-/.test(x)); return m || ''; }"
    )
    assert code.startswith("03-"), f"unexpected first code: {code}"
    # Click again to sort desc
    page.get_by_role("columnheader", name="物料编码").click()
    code = page.evaluate(
        "() => { const row = document.querySelector('tbody tr'); if(!row) return ''; const tds = Array.from(row.querySelectorAll('td')); const m = tds.map(td => td.innerText.trim()).find(x => /^\\d{2}-/.test(x)); return m || ''; }"
    )
    assert code.startswith("07-"), f"unexpected first code: {code}"


@pytest.mark.e2e
def test_query_param_prefill_triggers_search(serve_frontend, base_url: str, page: Page):
    page.add_init_script("localStorage.setItem('token','testtoken')")
    page.route("**/api/auth/verify", lambda r: r.fulfill(status=200, json={"ok": True}))
    page.route(
        "**/api/mto/PARAM123",
        lambda r: r.fulfill(status=200, json={"parent_item": {"mto_number": "PARAM123"}, "child_items": [{"material_code": "07-P001"}], "data_source": "live"}),
    )
    page.route("**/api/mto/PARAM123/related-orders", lambda r: r.fulfill(status=200, json={"orders": {}, "documents": {}}))

    page.goto(f"{base_url}/dashboard.html?mto=PARAM123")
    expect(page.get_by_text("成功查询到 1 条BOM组件记录")).to_be_visible()


@pytest.mark.e2e
def test_logout_redirects_to_login(serve_frontend, base_url: str, page: Page):
    page.add_init_script("localStorage.setItem('token','testtoken')")
    page.route("**/api/auth/verify", lambda r: r.fulfill(status=200, json={"ok": True}))
    page.goto(f"{base_url}/dashboard.html")

    # Open user menu and click logout
    page.get_by_role("button", name="用户").click()
    page.get_by_role("button", name="退出登录").click()
    page.wait_for_url(f"{base_url}/")
    expect(page.get_by_role("button", name="登录")).to_be_visible()
