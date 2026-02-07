import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
def test_sync_panel_status_and_trigger(serve_frontend, base_url: str, page: Page):
    # Pre-auth
    page.add_init_script("localStorage.setItem('token','testtoken')")

    # Common auth
    page.route("**/api/auth/verify", lambda route: route.fulfill(status=200, json={"ok": True}))

    # Initial status: idle
    page.route(
        "**/api/sync/status",
        lambda route: route.fulfill(
            status=200,
            json={
                "is_running": False,
                "progress": 0,
                "current_task": None,
                "last_sync": "",
                "records_synced": None,
            },
        ),
    )

    # Config
    page.route(
        "**/api/sync/config",
        lambda route: route.fulfill(status=200, json={"manual_sync_default_days": 30}),
    )

    page.goto(f"{base_url}/sync.html")
    expect(page.get_by_role("heading", name="同步管理")).to_be_visible()
    expect(page.get_by_text("空闲")).to_be_visible()

    # When triggerSync is clicked, return a running status on fetchStatus()
    def handle_trigger(route):
        # Verify payload has expected fields
        payload = route.request.post_data_json
        assert isinstance(payload, dict)
        # Default daysBack from config is 30 and force default is false
        assert payload.get("days_back") == 30
        assert payload.get("force") is False
        # After trigger, next status shows running
        page.unroute("**/api/sync/status")
        page.route(
            "**/api/sync/status",
            lambda r: r.fulfill(
                status=200,
                json={
                    "is_running": True,
                    "progress": 25,
                    "current_task": "Syncing recent changes...",
                    "last_sync": "2026-02-06T12:00:00Z",
                    "records_synced": 42,
                },
            ),
        )
        route.fulfill(status=200, json={"ok": True})

    page.route("**/api/sync/trigger", handle_trigger)

    # Trigger and assert state changes
    page.get_by_role("button", name="开始同步").click()
    expect(page.get_by_text("同步中...")).to_be_visible()
    # Progress bar should exist
    expect(page.locator("div[style*='width: 25%']")).to_be_visible()
