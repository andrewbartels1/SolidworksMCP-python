"""Direct branch tests for solidworks_mcp.cache.response_cache."""

from __future__ import annotations

import json

from solidworks_mcp.cache.response_cache import CachePolicy, ResponseCache


def test_evict_oldest_is_noop_on_empty_cache() -> None:
    cache = ResponseCache(CachePolicy(enabled=True, max_entries=2))
    cache._evict_oldest_unlocked()
    assert cache.get("missing") is None


def test_normalize_payload_falls_back_to_string_on_json_error(monkeypatch) -> None:
    cache = ResponseCache(CachePolicy(enabled=True, max_entries=2))

    original_dumps = json.dumps
    calls = {"count": 0}

    def _failing_once(payload, *args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise TypeError("boom")
        return original_dumps(payload, *args, **kwargs)

    monkeypatch.setattr("solidworks_mcp.cache.response_cache.json.dumps", _failing_once)

    normalized = cache._normalize_payload(object())

    assert isinstance(normalized, str)
    assert normalized.startswith('"')


def test_cache_get_disabled_returns_none() -> None:
    """Disabled cache should always return None on get."""
    cache = ResponseCache(CachePolicy(enabled=False, max_entries=2))
    assert cache.get("missing") is None


def test_cache_set_disabled_noop() -> None:
    """Disabled cache should not store entries."""
    cache = ResponseCache(CachePolicy(enabled=False, max_entries=1))
    cache.set("key", "value")
    assert cache._entries == {}


def test_cache_get_removes_expired_entry(monkeypatch) -> None:
    """Expired entries should be evicted on get."""
    from solidworks_mcp.cache.response_cache import _CacheEntry

    cache = ResponseCache(CachePolicy(enabled=True, max_entries=2))
    cache._entries["key"] = _CacheEntry(value="v", created_at=0.0, expires_at=0.0)
    monkeypatch.setattr("solidworks_mcp.cache.response_cache.time.time", lambda: 10.0)
    assert cache.get("key") is None
    assert "key" not in cache._entries


def test_cache_set_evicts_oldest_when_full(monkeypatch) -> None:
    """When full, cache should evict the oldest entry."""
    cache = ResponseCache(CachePolicy(enabled=True, max_entries=1))
    monkeypatch.setattr("solidworks_mcp.cache.response_cache.time.time", lambda: 1.0)
    cache.set("old", "v1", ttl_seconds=10)
    monkeypatch.setattr("solidworks_mcp.cache.response_cache.time.time", lambda: 2.0)
    cache.set("new", "v2", ttl_seconds=10)
    assert "new" in cache._entries
    assert "old" not in cache._entries
