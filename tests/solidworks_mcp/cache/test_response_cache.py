"""Direct branch tests for src.solidworks_mcp.cache.response_cache."""

from __future__ import annotations

import json

from src.solidworks_mcp.cache.response_cache import CachePolicy, ResponseCache


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

    monkeypatch.setattr(
        "src.solidworks_mcp.cache.response_cache.json.dumps", _failing_once
    )

    normalized = cache._normalize_payload(object())

    assert isinstance(normalized, str)
    assert normalized.startswith('"')
