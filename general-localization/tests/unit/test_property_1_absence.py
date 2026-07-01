# Feature: message-localization, Property 1: Absence detection and named failure
"""Property-based test for Property 1 (Absence detection and named failure).

Validates: Requirements 1.7, 2.3

For any value, ``is_absent`` returns True exactly when the value is None, not a
string, empty, or whitespace-only, and False otherwise. For any absent value,
``require(name, value)`` raises ``ConfigError`` whose message contains ``name``;
for any non-absent value it returns the stripped string.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from config_validation import ConfigError, is_absent, require


# --- Input categories -------------------------------------------------------

# Non-string values: ints, floats, bools, lists, dicts, tuples, None-adjacent.
_non_string_values = st.one_of(
    st.none(),
    st.integers(),
    st.floats(allow_nan=True, allow_infinity=True),
    st.booleans(),
    st.lists(st.integers()),
    st.dictionaries(st.text(), st.integers()),
    st.tuples(st.integers()),
    st.binary(),
)

# Whitespace-only strings (incl. tabs/newlines and the empty string).
_blank_strings = st.text(alphabet=" \t\n\r\f\v", min_size=0, max_size=10)

# Valid non-blank strings: guaranteed to contain at least one non-whitespace char.
_valid_strings = st.text(min_size=1).filter(lambda s: s.strip() != "")

# Any value across all categories.
_any_value = st.one_of(_non_string_values, _blank_strings, _valid_strings)


def _expected_absent(value: object) -> bool:
    """Reference oracle mirroring the spec definition of absence."""
    if value is None:
        return True
    if not isinstance(value, str):
        return True
    return value.strip() == ""


# --- Properties -------------------------------------------------------------

@settings(max_examples=200)
@given(value=_any_value)
def test_is_absent_matches_specification(value: object) -> None:
    """``is_absent`` is True iff None / non-str / empty / whitespace-only."""
    assert is_absent(value) == _expected_absent(value)


@settings(max_examples=200)
@given(name=st.text(min_size=1), value=_any_value)
def test_require_raises_named_error_for_absent_values(
    name: str, value: object
) -> None:
    """For absent values ``require`` raises ConfigError containing ``name``;
    for non-absent values it returns the stripped string."""
    if _expected_absent(value):
        with pytest.raises(ConfigError) as exc_info:
            require(name, value)
        assert name in str(exc_info.value)
    else:
        # Non-absent values are necessarily non-blank strings here.
        assert require(name, value) == value.strip()


@settings(max_examples=100)
@given(value=_non_string_values)
def test_non_string_values_are_absent(value: object) -> None:
    """Non-string values (incl. None) are always absent."""
    assert is_absent(value) is True


@settings(max_examples=100)
@given(value=_blank_strings)
def test_blank_strings_are_absent(value: str) -> None:
    """Empty and whitespace-only strings are absent."""
    assert is_absent(value) is True


@settings(max_examples=100)
@given(value=_valid_strings)
def test_valid_strings_are_present_and_stripped(value: str) -> None:
    """Non-blank strings are present and ``require`` returns them stripped."""
    assert is_absent(value) is False
    assert require("SOME_CONSTANT", value) == value.strip()
