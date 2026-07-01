# Feature: message-localization, Property 2: Hold-message validation
"""Property-based test for ``require_hold_message`` (Property 2).

Property 2: Hold-message validation
*For any* string, ``require_hold_message(language, value)`` returns the value
when it is non-blank and at most 3000 characters, and otherwise raises a
``ConfigError`` whose message names ``language``. (Empty, whitespace-only, and
over-length inputs are all rejected.)

Validates: Requirements 1.5, 3.6
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from config_validation import ConfigError, require_hold_message

MAX_LEN = 3000

# A few representative language labels used by the Localized_Queue_Flow. The
# property must hold for any language label, so we draw from this set.
LANGUAGES = ["English", "Spanish", "Portuguese"]

# Characters that survive str.strip() (no leading/trailing whitespace handling
# concerns when used to build the *core* of a value).
_NON_WS = st.characters(blacklist_categories=("Cc", "Cs", "Zs", "Zl", "Zp"))


def _is_blank(value: str) -> bool:
    return value.strip() == ""


# ---------------------------------------------------------------------------
# Core property: holds across arbitrary strings of arbitrary length.
# ---------------------------------------------------------------------------
@settings(max_examples=300)
@given(
    language=st.sampled_from(LANGUAGES),
    value=st.text(max_size=3100),
)
def test_hold_message_validation_property(language: str, value: str) -> None:
    stripped = value.strip()
    if _is_blank(value) or len(stripped) > MAX_LEN:
        # Blank or over-length -> must raise ConfigError naming the language.
        with pytest.raises(ConfigError) as exc:
            require_hold_message(language, value)
        assert language in str(exc.value)
    else:
        # Non-blank and within the ceiling -> returns the stripped value.
        result = require_hold_message(language, value)
        assert result == stripped
        assert 1 <= len(result) <= MAX_LEN


# ---------------------------------------------------------------------------
# Valid in-range, non-blank strings always return the stripped value.
# ---------------------------------------------------------------------------
@settings(max_examples=150)
@given(
    language=st.sampled_from(LANGUAGES),
    core=st.text(alphabet=_NON_WS, min_size=1, max_size=MAX_LEN),
    lead=st.text(alphabet=" \t\n", max_size=5),
    trail=st.text(alphabet=" \t\n", max_size=5),
)
def test_valid_non_blank_returns_stripped(
    language: str, core: str, lead: str, trail: str
) -> None:
    value = lead + core + trail
    # core has no surrounding whitespace, so stripping the padded value yields core.
    result = require_hold_message(language, value)
    assert result == value.strip()
    assert len(result) <= MAX_LEN


# ---------------------------------------------------------------------------
# Empty and whitespace-only inputs are always rejected, naming the language.
# ---------------------------------------------------------------------------
@settings(max_examples=150)
@given(
    language=st.sampled_from(LANGUAGES),
    value=st.text(alphabet=" \t\n\r\f\v", max_size=20),
)
def test_blank_inputs_rejected(language: str, value: str) -> None:
    with pytest.raises(ConfigError) as exc:
        require_hold_message(language, value)
    assert language in str(exc.value)


# ---------------------------------------------------------------------------
# The 3000-char boundary: exactly 3000 passes, 3001 fails.
# ---------------------------------------------------------------------------
@settings(max_examples=100)
@given(language=st.sampled_from(LANGUAGES))
def test_boundary_exactly_max_len_passes(language: str) -> None:
    value = "a" * MAX_LEN
    result = require_hold_message(language, value)
    assert result == value
    assert len(result) == MAX_LEN


@settings(max_examples=100)
@given(
    language=st.sampled_from(LANGUAGES),
    overflow=st.integers(min_value=1, max_value=200),
)
def test_boundary_over_max_len_fails(language: str, overflow: int) -> None:
    value = "a" * (MAX_LEN + overflow)
    with pytest.raises(ConfigError) as exc:
        require_hold_message(language, value)
    assert language in str(exc.value)


def test_boundary_3001_fails_3000_passes_examples() -> None:
    # Explicit unit assertions at the exact boundary.
    assert require_hold_message("English", "x" * 3000) == "x" * 3000
    with pytest.raises(ConfigError):
        require_hold_message("English", "x" * 3001)
