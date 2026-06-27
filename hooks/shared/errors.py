"""Custom exceptions for the v2 hook system."""


class HookError(Exception):
    """Base class for all hook errors."""


class ConfigError(HookError):
    """Raised when configuration is missing or invalid."""


class ValidationError(HookError):
    """Raised when a deterministic (Category 1) validation fails."""


class LLMError(HookError):
    """Raised when an LLM (Category 2) call fails or returns unparseable output."""
