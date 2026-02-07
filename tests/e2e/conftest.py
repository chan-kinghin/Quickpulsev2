"""E2E test fixtures for serving frontend and mocking API.

Uses pytest-playwright sync fixtures to drive the browser.
"""

import os
import sys
import socket
import subprocess
import time
from contextlib import closing
from pathlib import Path
from typing import Iterator

import pytest
from playwright.sync_api import Page


def _wait_for_port(host: str, port: int, timeout: float = 10.0) -> None:
    """Wait until the TCP port is accepting connections."""
    start = time.time()
    while time.time() - start < timeout:
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.settimeout(0.5)
            try:
                if sock.connect_ex((host, port)) == 0:
                    return
            except OSError:
                pass
        time.sleep(0.1)
    raise RuntimeError(f"Server on {host}:{port} did not start within {timeout}s")


@pytest.fixture(scope="session")
def base_url() -> str:
    return "http://localhost:8000"


@pytest.fixture(scope="session")
def serve_frontend(base_url: str) -> Iterator[None]:
    """Serve src/frontend via python http.server for E2E tests.

    Starts a background web server and shuts it down after the session.
    """
    frontend_dir = Path(__file__).resolve().parent.parent.parent / "src" / "frontend"
    assert frontend_dir.exists(), f"Frontend directory not found: {frontend_dir}"

    env = os.environ.copy()
    # Use unbuffered output to avoid hanging on shutdown
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", "8000"],
        cwd=str(frontend_dir),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_port("127.0.0.1", 8000, timeout=15)
        yield
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture()
def login_as_test_user(page: Page, base_url: str) -> None:
    """Pre-authenticate the app by setting a fake token in localStorage."""
    page.add_init_script("localStorage.setItem('token','testtoken')")


@pytest.fixture()
def mock_common_api(page: Page) -> None:
    """Default API mocks that keep pages stable without a backend."""

    # Auth verification used by authGuard() on protected pages
    page.route("**/api/auth/verify", lambda route: route.fulfill(status=200, json={"ok": True}))

    # Fallbacks for endpoints that may appear in flows but are optional in some tests
    page.route("**/api/sync/config", lambda route: route.fulfill(status=200, json={"manual_sync_default_days": 30}))
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


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):  # type: ignore[override]
    """Ensure downloads are accepted in headless context."""
    return {**(browser_context_args or {}), "accept_downloads": True}
