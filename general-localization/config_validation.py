"""Pure configuration-validation helpers for ``GeneralLocalizationStack``.

These functions hold the testable logic behind fail-closed config resolution
(Requirements 1.7, 2.2, 2.3), hold-message validation (Requirements 1.5, 3.6),
and boolean locale-enablement parsing (Requirement 10.4). They are deliberately
free of any CDK or boto3 dependency so they can be property-tested in isolation.
"""

from __future__ import annotations

# Recognized truthy tokens for parse_bool. String comparison is case-insensitive
# and whitespace-trimmed; the Python bool True is also accepted directly.
_TRUTHY_TOKENS: frozenset[str] = frozenset({"true", "1", "yes", "on"})


class ConfigError(Exception):
    """Raised when a required configuration value is absent or invalid."""


def is_absent(value: object) -> bool:
    """Return True when ``value`` is absent.

    A value is considered absent when it is ``None``, not a ``str``, the empty
    string, or whitespace-only. Any other (non-blank) string is present.
    """
    if value is None:
        return True
    if not isinstance(value, str):
        return True
    return value.strip() == ""


def require(name: str, value: object) -> str:
    """Return the stripped ``value`` or raise ``ConfigError`` naming ``name``.

    Used to resolve every mandatory config constant before any resource is
    defined, so a missing value halts synthesis with a message identifying the
    offending constant.
    """
    if is_absent(value):
        raise ConfigError(f"Required configuration value '{name}' is missing or empty.")
    # is_absent guarantees value is a non-blank str here.
    return value.strip()  # type: ignore[union-attr]


def parse_bool(value: object) -> bool:
    """Map recognized truthy tokens to True; everything else to False.

    Accepts the Python ``True`` boolean directly and the case-insensitive,
    whitespace-trimmed string tokens "true", "1", "yes", and "on". Any other
    value -- including ``None``, missing keys, non-strings, and unrecognized
    strings -- returns False. This makes "missing or unrecognized" default to
    disabled (Requirement 10.4).
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in _TRUTHY_TOKENS
    return False


def require_hold_message(language: str, value: object, max_len: int = 3000) -> str:
    """Return the stripped hold-message text or raise ``ConfigError``.

    Combines ``require`` (rejecting absent/blank values) with a length ceiling.
    The error message names ``language`` so the operator can tell which
    hold-message constant is at fault when it is absent or over-length.
    """
    if is_absent(value):
        raise ConfigError(f"Hold message for '{language}' is missing or empty.")
    stripped = value.strip()  # type: ignore[union-attr]
    if len(stripped) > max_len:
        raise ConfigError(
            f"Hold message for '{language}' exceeds the maximum length of "
            f"{max_len} characters (got {len(stripped)})."
        )
    return stripped
