"""E2E tests for the 物料分组 (material_group_name) column.

Phase 1 of PLAN_material_category_display_2026-05-09.md — verifies the new
column renders correctly in both the table and the BOM card view, with the
mocked API returning realistic group names sourced from BD_MATERIAL.MaterialGroup.
"""

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect


_SCREENSHOT_DIR = Path(__file__).parent
_SCREENSHOT_DIR.mkdir(exist_ok=True)


def _mock_mto_with_groups(page: Page, mto: str = "AK2510034") -> None:
    """Mock /api/mto/<mto> with children that exercise material_group_name."""
    page.route("**/api/auth/verify", lambda route: route.fulfill(status=200, json={"ok": True}))
    page.route(
        f"**/api/mto/{mto}*",
        lambda route: route.fulfill(
            status=200,
            json={
                "mto_number": mto,
                "parent_item": {
                    "mto_number": mto,
                    "customer_name": "刀刀电子",
                    "delivery_date": "2026-06-01T00:00:00",
                },
                "child_items": [
                    # 07.xx 成品 — group sourced from SAL_SaleOrder
                    {
                        "material_code": "07.02.057",
                        "material_name": "泳镜成品 A",
                        "specification": "",
                        "aux_attributes": "",
                        "material_type_code": 1,
                        "material_type": "成品",
                        "material_group_name": "泳镜",
                        "is_finished_goods": True,
                        "sales_order_qty": 1000,
                        "prod_instock_real_qty": 800,
                    },
                    {
                        "material_code": "07.41.001",
                        "material_name": "硅胶防水袋",
                        "specification": "",
                        "aux_attributes": "",
                        "material_type_code": 1,
                        "material_type": "成品",
                        "material_group_name": "硅胶防水袋",
                        "is_finished_goods": True,
                        "sales_order_qty": 500,
                        "prod_instock_real_qty": 500,
                    },
                    # 05.xx 自制件 — group sourced from PPBOM
                    {
                        "material_code": "05.02.08.037",
                        "material_name": "镜框",
                        "specification": "",
                        "aux_attributes": "",
                        "material_type_code": 1,
                        "material_type": "自制",
                        "material_group_name": "镜框（已印刷）",
                        "is_finished_goods": False,
                        "prod_instock_must_qty": 1500,
                        "prod_instock_real_qty": 1200,
                        "pick_actual_qty": 1200,
                    },
                    # 03.xx 外购件
                    {
                        "material_code": "03.23.009",
                        "material_name": "彩贴纸",
                        "specification": "100x80mm",
                        "aux_attributes": "红色",
                        "material_type_code": 2,
                        "material_type": "包材",
                        "material_group_name": "贴纸",
                        "is_finished_goods": False,
                        "purchase_order_qty": 2000,
                        "purchase_stock_in_qty": 2000,
                        "pick_actual_qty": 1800,
                    },
                    # Edge case: empty group name (synthetic row / older data) → "-"
                    {
                        "material_code": "08.99.999",
                        "material_name": "无分组测试件",
                        "specification": "",
                        "aux_attributes": "",
                        "material_type_code": 1,
                        "material_type": "自制",
                        "material_group_name": "",
                        "is_finished_goods": False,
                        "prod_instock_must_qty": 100,
                    },
                ],
                "data_source": "live",
            },
        ),
    )
    page.route(
        f"**/api/mto/{mto}/related-orders",
        lambda route: route.fulfill(
            status=200,
            json={"orders": {}, "documents": {}},
        ),
    )


@pytest.mark.e2e
def test_material_group_column_renders_in_table(serve_frontend, base_url: str, page: Page):
    """物料分组 column appears in table with localised group names."""
    page.add_init_script("localStorage.setItem('token','testtoken')")
    _mock_mto_with_groups(page)
    page.goto(f"{base_url}/dashboard.html")

    page.locator("#mto-search").fill("AK2510034")
    page.keyboard.press("Enter")
    expect(page.get_by_role("heading", name="BOM组件明细")).to_be_visible()

    # Column header exists & visible (sticky thead defeats some Playwright checks; use JS)
    header_visible = page.evaluate(
        "() => { const th = [...document.querySelectorAll('th')]"
        ".find(el => el.textContent.includes('物料分组'));"
        " return th ? !th.classList.contains('col-hidden') : false }"
    )
    assert header_visible, "物料分组 column header should be visible by default"

    # Body cells render the expected group names
    cell_texts = page.evaluate("""
        () => {
            const items = [];
            const tbodyRows = document.querySelectorAll('tbody tr');
            tbodyRows.forEach(tr => {
                const code = tr.querySelector('td:nth-child(2)')?.innerText?.trim() || '';
                // Find the material_group_name cell — its colVisible binding references that key.
                // We use a more robust selector: the td whose preceding header has '物料分组'.
                const tds = [...tr.querySelectorAll('td')];
                const allTh = [...document.querySelectorAll('thead th')];
                const idx = allTh.findIndex(th => th.innerText.includes('物料分组'));
                items.push({ code, group: tds[idx]?.innerText?.trim() ?? null });
            });
            return items;
        }
    """)

    code_to_group = {row["code"]: row["group"] for row in cell_texts}
    assert code_to_group.get("07.02.057") == "泳镜", code_to_group
    assert code_to_group.get("07.41.001") == "硅胶防水袋", code_to_group
    assert code_to_group.get("05.02.08.037") == "镜框（已印刷）", code_to_group
    assert code_to_group.get("03.23.009") == "贴纸", code_to_group
    # Empty group should degrade to '-'
    assert code_to_group.get("08.99.999") == "-", code_to_group

    page.screenshot(path=str(_SCREENSHOT_DIR / "material_group_column_proof.png"), full_page=True)


@pytest.mark.e2e
def test_material_group_column_is_sortable(serve_frontend, base_url: str, page: Page):
    """Clicking the header sorts rows by group name asc / desc."""
    page.add_init_script("localStorage.setItem('token','testtoken')")
    _mock_mto_with_groups(page)
    page.goto(f"{base_url}/dashboard.html")

    page.locator("#mto-search").fill("AK2510034")
    page.keyboard.press("Enter")
    expect(page.get_by_role("heading", name="BOM组件明细")).to_be_visible()

    # Click the column header twice — first sort asc, then desc.
    def click_group_header():
        page.evaluate("""
            () => {
                const th = [...document.querySelectorAll('th')]
                    .find(el => el.textContent.includes('物料分组'));
                th?.click();
            }
        """)

    click_group_header()
    page.wait_for_timeout(100)
    asc_order = page.evaluate("""
        () => {
            const allTh = [...document.querySelectorAll('thead th')];
            const idx = allTh.findIndex(th => th.innerText.includes('物料分组'));
            return [...document.querySelectorAll('tbody tr')]
                .map(tr => tr.querySelectorAll('td')[idx]?.innerText?.trim());
        }
    """)
    # Ascending should place '-' (empty → '-') first or last depending on sort impl,
    # and group names in lexical order. Assert the non-empty names are in order.
    non_empty_asc = [g for g in asc_order if g and g != "-"]
    assert non_empty_asc == sorted(non_empty_asc), (
        f"Expected ascending sort; got {non_empty_asc}"
    )

    click_group_header()
    page.wait_for_timeout(100)
    desc_order = page.evaluate("""
        () => {
            const allTh = [...document.querySelectorAll('thead th')];
            const idx = allTh.findIndex(th => th.innerText.includes('物料分组'));
            return [...document.querySelectorAll('tbody tr')]
                .map(tr => tr.querySelectorAll('td')[idx]?.innerText?.trim());
        }
    """)
    non_empty_desc = [g for g in desc_order if g and g != "-"]
    assert non_empty_desc == sorted(non_empty_desc, reverse=True), (
        f"Expected descending sort; got {non_empty_desc}"
    )


@pytest.mark.e2e
def test_material_group_visible_in_bom_card_view(serve_frontend, base_url: str, page: Page):
    """BOM card view (used on narrow viewports) also shows 物料分组."""
    # Use a narrow viewport so the bom-cards layout triggers if media queries gate it.
    page.set_viewport_size({"width": 480, "height": 900})
    page.add_init_script("localStorage.setItem('token','testtoken')")
    _mock_mto_with_groups(page)
    page.goto(f"{base_url}/dashboard.html")

    page.locator("#mto-search").fill("AK2510034")
    page.keyboard.press("Enter")
    expect(page.get_by_role("heading", name="BOM组件明细")).to_be_visible()

    # Either bom-cards or the table is shown depending on CSS; check that
    # 物料分组 labels appear somewhere on the page.
    has_label = page.evaluate("""
        () => {
            const all = document.body.innerText;
            return all.includes('物料分组') && all.includes('硅胶防水袋');
        }
    """)
    assert has_label, "物料分组 label and at least one group name should appear in narrow viewport"

    page.screenshot(path=str(_SCREENSHOT_DIR / "material_group_bom_card_proof.png"), full_page=True)


@pytest.mark.e2e
def test_material_group_can_be_hidden_via_column_settings(serve_frontend, base_url: str, page: Page):
    """User can toggle 物料分组 column off via the column settings menu."""
    page.add_init_script("localStorage.setItem('token','testtoken')")
    _mock_mto_with_groups(page)
    page.goto(f"{base_url}/dashboard.html")

    page.locator("#mto-search").fill("AK2510034")
    page.keyboard.press("Enter")
    expect(page.get_by_role("heading", name="BOM组件明细")).to_be_visible()

    # Verify visible initially
    visible_before = page.evaluate(
        "() => { const th = [...document.querySelectorAll('th')]"
        ".find(el => el.textContent.includes('物料分组'));"
        " return th ? !th.classList.contains('col-hidden') : false }"
    )
    assert visible_before, "物料分组 should be visible before toggle"

    # Open column settings and click the 物料分组 toggle
    page.locator("button[aria-label='Column settings']").click()
    page.locator(".column-settings .column-settings-item:has-text('物料分组') input").click()
    page.keyboard.press("Escape")

    # Header should be hidden
    page.wait_for_timeout(200)
    hidden_after = page.evaluate(
        "() => { const th = [...document.querySelectorAll('th')]"
        ".find(el => el.textContent.includes('物料分组'));"
        " return th ? th.classList.contains('col-hidden') : true }"
    )
    assert hidden_after, "物料分组 should be hidden after toggling it off"
