"""
Rate limiting for API endpoints.
"""

from collections import defaultdict
import time
from typing import Any

from ..config import SolidWorksMCPConfig


class RateLimiter:
    """Simple in-memory rate limiter."""

    def __init__(self, max_requests: int, time_window: int = 60):
        """Initialize this object.
        
        Args:
            max_requests (int): Describe max requests.
            time_window (int): Describe time window.
        
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, client_id: str) -> bool:
        """Check if client is within rate limits."""
        now = time.time()
        window_start = now - self.time_window

        # Remove old requests
        self.requests[client_id] = [
            req_time for req_time in self.requests[client_id] if req_time > window_start
        ]

        # Check if under limit
        if len(self.requests[client_id]) < self.max_requests:
            self.requests[client_id].append(now)
            return True

        return False


# Global rate limiter instance
_rate_limiter: RateLimiter | None = None


def setup_rate_limiting(mcp: Any, config: SolidWorksMCPConfig) -> None:
    """Initialize in-memory rate limiting.

    Args:
        mcp: Active MCP server instance (reserved for future middleware hooks).
        config: Loaded server configuration containing rate limit settings.
    """
    global _rate_limiter
    _rate_limiter = RateLimiter(
        max_requests=config.rate_limit_per_minute,
        time_window=60,  # 1 minute
    )


def check_rate_limit(client_id: str) -> bool:
    """Check if client is within rate limits."""
    if _rate_limiter is None:
        return True
    return _rate_limiter.is_allowed(client_id)
