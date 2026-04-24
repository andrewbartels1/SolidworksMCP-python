"""In-memory response cache with TTL support for adapter operations.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from threading import RLock
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class CachePolicy:
    """Cache policy options for adapter responses.
    
    Attributes:
        default_ttl_seconds (int): The default ttl seconds value.
        enabled (bool): The enabled value.
        max_entries (int): The max entries value.
    """

    enabled: bool = True
    default_ttl_seconds: int = 60
    max_entries: int = 512


@dataclass
class _CacheEntry(Generic[T]):
    """Internal cache entry with expiration metadata.
    
    Attributes:
        created_at (float): The created at value.
        expires_at (float): The expires at value.
        value (T): The value value.
    """

    value: T
    expires_at: float
    created_at: float


class ResponseCache:
    """Thread-safe in-memory cache for adapter response objects.
    
    Args:
        policy (CachePolicy): The policy value.
    
    Attributes:
        _lock (Any): The lock value.
        _policy (Any): The policy value.
    """

    def __init__(self, policy: CachePolicy) -> None:
        """Initialize this cache.
        
        Args:
            policy (CachePolicy): The policy value.
        
        Returns:
            None: None.
        """
        self._policy = policy
        self._entries: dict[str, _CacheEntry[object]] = {}
        self._lock = RLock()

    @property
    def enabled(self) -> bool:
        """Return whether caching is enabled.
        
        Returns:
            bool: True if enabled, otherwise False.
        """
        return self._policy.enabled

    def make_key(self, operation: str, payload: object) -> str:
        """Build a deterministic cache key from an operation payload.
        
        Args:
            operation (str): Callable object executed by the helper.
            payload (object): The payload value.
        
        Returns:
            str: The resulting text value.
        """
        normalized = self._normalize_payload(payload)
        raw = f"{operation}:{normalized}".encode()
        return hashlib.sha256(raw).hexdigest()

    def get(self, key: str) -> object | None:
        """Fetch a cached value when present and unexpired.
        
        Args:
            key (str): The key value.
        
        Returns:
            object | None: The result produced by the operation.
        """
        if not self._policy.enabled:
            return None

        now = time.time()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                self._entries.pop(key, None)
                return None
            return entry.value

    def set(self, key: str, value: object, ttl_seconds: int | None = None) -> None:
        """Store a cache value with expiration.
        
        Args:
            key (str): The key value.
            value (object): The value value.
            ttl_seconds (int | None): The ttl seconds value. Defaults to None.
        
        Returns:
            None: None.
        """
        if not self._policy.enabled:
            return

        ttl = (
            ttl_seconds if ttl_seconds is not None else self._policy.default_ttl_seconds
        )
        now = time.time()
        entry = _CacheEntry(value=value, created_at=now, expires_at=now + max(ttl, 1))

        with self._lock:
            if len(self._entries) >= self._policy.max_entries:
                self._evict_oldest_unlocked()
            self._entries[key] = entry

    def _evict_oldest_unlocked(self) -> None:
        """Remove one oldest entry while lock is already held.
        
        Returns:
            None: None.
        """
        if not self._entries:
            return
        oldest_key = min(
            self._entries,
            key=lambda cache_key: self._entries[cache_key].created_at,
        )
        self._entries.pop(oldest_key, None)

    def _normalize_payload(self, payload: object) -> str:
        """Normalize payload into a stable JSON string.
        
        Args:
            payload (object): The payload value.
        
        Returns:
            str: The resulting text value.
        """
        try:
            return json.dumps(
                payload, sort_keys=True, default=str, separators=(",", ":")
            )
        except (TypeError, ValueError):
            return json.dumps(str(payload), sort_keys=True)
