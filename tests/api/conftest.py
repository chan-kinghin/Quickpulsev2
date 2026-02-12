"""Shared fixtures for API endpoint tests."""

import pytest

from src.api.middleware.rate_limit import limiter


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Reset rate limiter storage between tests to avoid 429s."""
    limiter.reset()
    yield
    limiter.reset()
