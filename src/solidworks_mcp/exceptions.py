"""Custom exceptions for SolidWorks MCP Server."""


class SolidWorksMCPError(Exception):
    """Base exception for SolidWorks MCP Server errors."""

    pass


class SolidWorksConnectionError(SolidWorksMCPError):
    """Exception raised when SolidWorks connection fails."""

    pass


class SolidWorksOperationError(SolidWorksMCPError):
    """Exception raised when SolidWorks operation fails."""

    pass


class ConfigurationError(SolidWorksMCPError):
    """Exception raised for configuration issues."""

    pass


class AuthenticationError(SolidWorksMCPError):
    """Exception raised for authentication failures."""

    pass


class RateLimitError(SolidWorksMCPError):
    """Exception raised when rate limit is exceeded."""

    pass


class InputRefused(ValueError):
    """The adapter checked an input against the document and refused it.

    An expected answer, not a fault: a section line that misses its view, a
    point with nothing to dimension. It is logged as one line, without a
    traceback, and the tools classify it as ``invalid_input``.
    """
