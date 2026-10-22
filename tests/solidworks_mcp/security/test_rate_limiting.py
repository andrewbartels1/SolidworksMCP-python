"""Tests for ``solidworks_mcp.security.rate_limiting``."""

from __future__ import annotations

import time
from types import SimpleNamespace

from solidworks_mcp.security import rate_limiting as rl_mod


def test_rate_limiter_window_and_global_setup(monkeypatch):
    """Test rate limiter window and global setup."""
    rl = rl_mod.RateLimiter(max_requests=2, time_window=5)

    # Fill limit
    assert rl.is_allowed("c1") is True
    assert rl.is_allowed("c1") is True
    assert rl.is_allowed("c1") is False

    # Advance time by replacing time.time to force expiry of old requests
    base = time.time()
    monkeypatch.setattr(rl_mod.time, "time", lambda: base + 10)
    assert rl.is_allowed("c1") is True

    cfg = SimpleNamespace(rate_limit_per_minute=1)
    rl_mod.setup_rate_limiting(object(), cfg)
    assert rl_mod.check_rate_limit("client") is True
    assert rl_mod.check_rate_limit("client") is False

    rl_mod._rate_limiter = None
    assert rl_mod.check_rate_limit("client") is True
