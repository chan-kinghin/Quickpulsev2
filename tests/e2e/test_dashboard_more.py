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

    # Clear input, blur, then re-focus to trigger @focus handler
    # (history dropdown only shows when input is empty/short AND on focus event)
    page.locator("#mto-search").fill("")
    page.locator("#mto-search").blur()
    page.wait_for_timeout(300)
    page.locator("#mto-search").click()
    dropdown = page.locator(".search-history")
    expect(dropdown).to_be_visible()
    expect(dropdown.get_by_text("AK0000002", exact=True)).to_be_visible()
    expect(dropdown.get_by_text("AK0000001", exact=True)).to_be_visible()

    # Pick older entry from history and verify result (mousedown is used in the component)
    page.locator(".search-history-item:has-text('AK0000001')").dispatch_event("mousedown")
    expect(page.get_by_text("成功查询到 1 条BOM组件记录")).to_be_visible()

    # Clear history and ensure dropdown no longer appears on re-focus
    page.locator("#mto-search").fill("")
    page.locator("#mto-search").blur()
    page.wait_for_timeout(300)
    page.locator("#mto-search").click()
    dropdown = page.locator(".search-history")
    expect(dropdown).to_be_visible()
    dropdown.get_by_role("button", name="清除").click()
    # blur + refocus to re-evaluate — history was cleared so nothing should show
    page.wait_for_timeout(300)
    page.locator("#mto-search").blur()
    page.wait_for_timeout(300)
    page.locator("#mto-search").click()
    expect(page.get_by_text("最近搜索")).not_to_be_visible()


@pytest.mark.e2e
def test_sorting_by_material_code(serve_frontend, base_url: str, page: Page):
    page.add_init_script("localStorage.setItem('token','testtoken')")
    page.route("**/api/auth/verify", lambda r: r.fulfill(status=200, json={"ok": True}))
    # Provide 3 rows for sort checks
    page.route(
        "**/api/mto/AK99999",
        lambda r: r.fulfill(
            status=200,
            json={
                "parent_item": {"mto_number": "AK99999"},
                "child_items": [
                    {"material_code": "07-P001", "material_name": "A", "material_type": "成品"},
                    {"material_code": "03-C002", "material_name": "B", "material_type": "包材"},
                    {"material_code": "05-C001", "material_name": "C", "material_type": "自制"},
                ],
                "data_source": "live",
            },
        ),
    )
    page.route("**/api/mto/AK99999/related-orders", lambda r: r.fulfill(status=200, json={"orders": {}, "documents": {}}))

    page.goto(f"{base_url}/dashboard.html")
    page.locator("#mto-search").fill("AK99999")
    page.keyboard.press("Enter")
    # Wait for table rows to render
    expect(page.get_by_role("heading", name="BOM组件明细")).to_be_visible()
    page.wait_for_timeout(500)

    first_code_js = (
        "() => { const row = document.querySelector('tbody tr'); if(!row) return '';"
        " const tds = Array.from(row.querySelectorAll('td'));"
        " const m = tds.map(td => td.innerText.trim()).find(x => /^\\d{2}-/.test(x));"
        " return m || ''; }"
    )

    # Click "物料编码" header via JS to sort asc (sticky headers block Playwright clicks)
    page.evaluate(
        "() => { const th = [...document.querySelectorAll('th')]"
        ".find(el => el.textContent.includes('物料编码')); if(th) th.click(); }"
    )
    page.wait_for_timeout(300)
    code = page.evaluate(first_code_js)
    assert code.startswith("03-"), f"unexpected first code after asc sort: {code}"

    # Click again to sort desc
    page.evaluate(
        "() => { const th = [...document.querySelectorAll('th')]"
        ".find(el => el.textContent.includes('物料编码')); if(th) th.click(); }"
    )
    page.wait_for_timeout(300)
    code = page.evaluate(first_code_js)
    assert code.startswith("07-"), f"unexpected first code after desc sort: {code}"


@pytest.mark.e2e
def test_query_param_prefill_triggers_search(serve_frontend, base_url: str, page: Page):
    page.add_init_script("localStorage.setItem('token','testtoken')")
    page.route("**/api/auth/verify", lambda r: r.fulfill(status=200, json={"ok": True}))
    page.route(
        "**/api/mto/AK12345",
        lambda r: r.fulfill(status=200, json={"parent_item": {"mto_number": "AK12345"}, "child_items": [{"material_code": "07-P001"}], "data_source": "live"}),
    )
    page.route("**/api/mto/AK12345/related-orders", lambda r: r.fulfill(status=200, json={"orders": {}, "documents": {}}))

    page.goto(f"{base_url}/dashboard.html?mto=AK12345")
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
