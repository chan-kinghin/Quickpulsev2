import pytest
from playwright.sync_api import Page, expect


def _mock_common_search(page: Page, mto: str = "AK2510034") -> None:
    page.route("**/api/auth/verify", lambda route: route.fulfill(status=200, json={"ok": True}))
    page.route(
        f"**/api/mto/{mto}",
        lambda route: route.fulfill(
            status=200,
            json={
                "parent_item": {"mto_number": mto, "customer_name": "客户", "delivery_date": "2025-02-01T00:00:00"},
                "child_items": [
                    {"material_code": "07-P001", "material_name": "成品 A", "sales_order_qty": 10, "prod_instock_real_qty": 8},
                    {"material_code": "05-C001", "material_name": "自制件 B", "prod_instock_must_qty": 5, "pick_actual_qty": 1},
                ],
                "data_source": "live",
            },
        ),
    )
    page.route(
        f"**/api/mto/{mto}/related-orders",
        lambda route: route.fulfill(
            status=200,
            json={
                "orders": {"sales_orders": [{"label": "销售订单", "bill_no": "SO0001"}]},
                "documents": {"sales_deliveries": [{"label": "发货单", "bill_no": "FH0001"}]},
            },
        ),
    )


@pytest.mark.e2e
def test_column_visibility_toggle_hides_header(serve_frontend, base_url: str, page: Page):
    page.add_init_script("localStorage.setItem('token','testtoken')")
    _mock_common_search(page)
    page.goto(f"{base_url}/dashboard.html")

    # Search to display the table
    page.locator("#mto-search").fill("AK2510034")
    page.keyboard.press("Enter")
    expect(page.get_by_role("heading", name="BOM组件明细")).to_be_visible()
    expect(page.get_by_role("columnheader", name="规格型号")).to_be_visible()

    # Open column settings and hide "规格型号"
    page.get_by_role("button", name="列设置").click()
    page.locator(".column-settings .column-settings-item:has-text('规格型号') input").click()
    # Close menu
    page.keyboard.press("Escape")

    # Header should disappear
    expect(page.get_by_role("columnheader", name="规格型号")).not_to_be_visible()


@pytest.mark.e2e
def test_related_orders_expand_collapse(serve_frontend, base_url: str, page: Page):
    page.add_init_script("localStorage.setItem('token','testtoken')")
    _mock_common_search(page)
    page.goto(f"{base_url}/dashboard.html")
    page.locator("#mto-search").fill("AK2510034")
    page.keyboard.press("Enter")
    expect(page.get_by_role("heading", name="订单关联图")).to_be_visible()

    # Collapse by clicking the header container
    page.locator("div.cursor-pointer:has(h2:has-text('订单关联图'))").click()
    # Expand again and check for a related item label
    page.locator("div.cursor-pointer:has(h2:has-text('订单关联图'))").click()
    expect(page.get_by_text("销售订单", exact=True)).to_be_visible()


@pytest.mark.e2e
def test_fullscreen_toggle_button_text(serve_frontend, base_url: str, page: Page):
    page.add_init_script("localStorage.setItem('token','testtoken')")
    _mock_common_search(page)
    page.goto(f"{base_url}/dashboard.html")
    page.locator("#mto-search").fill("AK2510034")
    page.keyboard.press("Enter")

    # Toggle full screen and verify button text changes
    btn = page.get_by_role("button", name="全屏")
    btn.click()
    expect(page.get_by_role("button", name="退出全屏")).to_be_visible()
    # Back to normal
    page.get_by_role("button", name="退出全屏").click()
    expect(page.get_by_role("button", name="全屏")).to_be_visible()
