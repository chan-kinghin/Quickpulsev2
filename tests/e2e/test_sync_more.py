import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
def test_sync_force_and_days_back_payload(serve_frontend, base_url: str, page: Page):
    # Pre-auth
    page.add_init_script("localStorage.setItem('token','testtoken')")
    page.route("**/api/auth/verify", lambda r: r.fulfill(status=200, json={"ok": True}))
    page.route("**/api/sync/status", lambda r: r.fulfill(status=200, json={"is_running": False}))
    page.route("**/api/sync/config", lambda r: r.fulfill(status=200, json={"manual_sync_default_days": 30}))

    captured = {"payload": None}

    def trigger_handler(route):
        captured["payload"] = route.request.post_data_json
        route.fulfill(status=200, json={"ok": True})

    page.route("**/api/sync/trigger", trigger_handler)

    page.goto(f"{base_url}/sync.html")
    expect(page.get_by_role("heading", name="同步管理")).to_be_visible()

    # Set daysBack to 7 and enable force
    page.locator("input[type='number']").fill("7")
    page.get_by_label("强制刷新").check()
    page.get_by_role("button", name="开始同步").click()

    assert captured["payload"] is not None
    assert captured["payload"].get("days_back") == 7
    assert captured["payload"].get("force") is True

