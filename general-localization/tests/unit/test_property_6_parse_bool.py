# Feature: message-localization, Property 6: Boolean enablement parsing defaults to disabled
"""Property-based test for ``config_validation.parse_bool``.

Property 6: Boolean enablement parsing defaults to disabled.

*For any* value, ``parse_bool`` returns ``True`` only for a recognized truthy
token and returns ``False`` for every other value, including ``None``, missing
keys, and unrecognized strings.

**Validates: Requirements 10.4**

The recognized truthy tokens are the Python ``bool`` ``True`` and the
case-insensitive, whitespace-trimmed strings "true", "1", "yes", and "on".
Everything else -- ``None``, missing keys (simulated via ``dict.get``),
non-strings, unrecognized strings, and the Python ``bool`` ``False`` -- maps to
``False``.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from config_validation import parse_bool

# The recognized truthy string tokens, per the implementation's token set.
_TRUTHY_TOKENS = ("true", "1", "yes", "on")


def _randomize_case(token: str, flags: list[bool]) -> str:
    """Return ``token`` with per-character case flips driven by ``flags``."""
    out = []
    for i, ch in enumerate(token):
        flip = flags[i % len(flags)] if flags else False
        out.append(ch.upper() if flip else ch.lower())
    return "".join(out)


# --- Strategies that each yield (value, expected_parse_bool_result) ----------

# 1) Recognized truthy string tokens in varied case with surrounding whitespace.
_WS = st.text(alphabet=" \t\n\r\f\v", max_size=4)


@st.composite
def _truthy_token_values(draw):
    token = draw(st.sampled_from(_TRUTHY_TOKENS))
    flags = draw(st.lists(st.booleans(), min_size=1, max_size=4))
    cased = _randomize_case(token, flags)
    value = draw(_WS) + cased + draw(_WS)
    return value, True


# 2) Unrecognized strings (random text that is NOT a truthy token once trimmed
#    and lowercased) -- including empty/whitespace-only strings.
def _is_recognized(s: str) -> bool:
    return s.strip().lower() in _TRUTHY_TOKENS


_unrecognized_strings = st.text(max_size=30).filter(lambda s: not _is_recognized(s)).map(
    lambda s: (s, False)
)

# 3) Non-string, non-bool values -> always False (None, ints, floats, bytes,
#    lists, dicts). Note int 1 is NOT the string "1", so it must be False.
_non_string_values = st.one_of(
    st.none(),
    st.integers(),
    st.floats(allow_nan=True, allow_infinity=True),
    st.binary(max_size=10),
    st.lists(st.integers(), max_size=5),
    st.dictionaries(st.text(max_size=3), st.integers(), max_size=3),
).map(lambda v: (v, False))

# 4) Python booleans -> the bool itself (True -> True, False -> False).
_bool_values = st.booleans().map(lambda b: (b, b))


_value_and_expected = st.one_of(
    _truthy_token_values(),
    _unrecognized_strings,
    _non_string_values,
    _bool_values,
)


@settings(max_examples=200)
@given(case=_value_and_expected)
def test_parse_bool_returns_true_only_for_recognized_truthy_tokens(case):
    """parse_bool is True only for a recognized truthy token, else False."""
    value, expected = case
    result = parse_bool(value)

    assert result is expected, (
        f"parse_bool({value!r}) returned {result!r}, expected {expected!r}"
    )

    # Reinforce the core invariant: a True result is only ever produced by a
    # recognized truthy token (Python True, or a trimmed/lowercased string in
    # the token set). Everything else must be False.
    if result is True:
        recognized = (value is True) or (
            isinstance(value, str) and value.strip().lower() in _TRUTHY_TOKENS
        )
        assert recognized, f"parse_bool({value!r}) was True but is not a recognized token"


@settings(max_examples=200)
@given(
    other_keys=st.dictionaries(
        st.text(max_size=5).filter(lambda k: k != "pt_BR"),
        st.text(max_size=5),
        max_size=4,
    )
)
def test_parse_bool_treats_missing_key_as_disabled(other_keys):
    """A missing config key (simulated via dict.get) parses as False.

    Mirrors how the stack resolves a locale flag that the operator never set:
    ``config.get("pt_BR")`` yields ``None`` -> disabled (Requirement 10.4).
    """
    assert parse_bool(other_keys.get("pt_BR")) is False


def test_parse_bool_none_and_false_are_disabled():
    """Explicit anchors: None and Python False are both disabled."""
    assert parse_bool(None) is False
    assert parse_bool(False) is False
