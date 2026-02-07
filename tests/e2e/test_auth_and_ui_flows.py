import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
def test_login_failure_shows_error(serve_frontend, base_url: str, page: Page):
    # Mock 401 with JSON error
    page.route(
        "**/api/auth/token",
        lambda route: route.fulfill(status=401, json={"detail": "用户名或密码错误"}),
    )

    page.goto(f"{base_url}/")
    page.locator("#username").fill("user")
    page.locator("#password").fill("wrong")
    page.get_by_role("button", name="登录").click()
    expect(page.get_by_text("用户名或密码错误")).to_be_visible()


@pytest.mark.e2e
def test_auth_guard_redirects_without_token(serve_frontend, base_url: str, page: Page):
    # Navigate directly to dashboard without token → should redirect to login
    page.goto(f"{base_url}/dashboard.html")
    page.wait_for_url(f"{base_url}/")
    expect(page.get_by_role("button", name="登录")).to_be_visible()


@pytest.mark.e2e
def test_auth_guard_invalid_token_redirects(serve_frontend, base_url: str, page: Page):
    page.add_init_script("localStorage.setItem('token','badtoken')")
    page.route("**/api/auth/verify", lambda route: route.fulfill(status=401))

    page.goto(f"{base_url}/dashboard.html")
    page.wait_for_url(f"{base_url}/")
    expect(page.get_by_role("button", name="登录")).to_be_visible()

