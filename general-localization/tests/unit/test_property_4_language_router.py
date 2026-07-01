# Feature: message-localization, Property 4: Internal language selection is total and correct
"""Property-based test for the internal language router (Property 4).

Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5

Property 4 (Internal language selection is total and correct):
    For any input value, ``select_queue_experience`` returns exactly one
    well-formed ``QueueSelection`` (it never raises and ``flow_key`` is always
    one of ``en``/``es``/``pt``, naming the matching internal path of the single
    Localized_Queue_Flow); and:
      - when the input is a ``$.LanguageCode`` value (java.util.Locale, e.g.
        ``es-US``) whose language sub-tag is ``es``, ``pt``, or ``en``, it
        returns that language with ``default_applied = False`` regardless of
        the region variant;
      - for every other input (absent, empty, or any unrecognized value) it
        returns English with ``default_applied = True``.

The router mirrors the flow's ``Compare`` block, which branches on
``$.LanguageCode`` with ``TextStartsWith`` on the sub-tag (``es`` / ``pt`` /
``en``).
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from language_router import (
    ENGLISH,
    PORTUGUESE,
    SPANISH,
    QueueSelection,
    select_queue_experience,
)

# The closed set of internal flow-path keys (Requirement 4: en/es/pt).
_VALID_FLOW_KEYS = {"en", "es", "pt"}

# Language sub-tag prefix -> expected (language, flow_key) for a match.
_PREFIX_EXPECTED = {
    "es": (SPANISH, "es"),
    "pt": (PORTUGUESE, "pt"),
    "en": (ENGLISH, "en"),
}

# Map a canonical language back to its flow_key, for well-formedness checks.
_LANG_FLOW_KEY = {SPANISH: "es", PORTUGUESE: "pt", ENGLISH: "en"}


def _matched_prefix(value: object) -> str | None:
    """The language sub-tag prefix the router would match (es/pt/en), or None.

    Mirrors the router/flow semantics: a string whose stripped form starts with
    es/pt/en (checked in that order) matches; anything else does not.
    """
    if isinstance(value, str):
        code = value.strip()
        for prefix in ("es", "pt", "en"):
            if code.startswith(prefix):
                return prefix
    return None


def _assert_well_formed(selection: object) -> None:
    """Every result is exactly one well-formed QueueSelection."""
    assert isinstance(selection, QueueSelection)
    assert selection.flow_key in _VALID_FLOW_KEYS
    assert selection.language in (ENGLISH, SPANISH, PORTUGUESE)
    # The language field must name the matching internal path.
    assert _LANG_FLOW_KEY[selection.language] == selection.flow_key
    assert isinstance(selection.default_applied, bool)


# Realistic $.LanguageCode values whose sub-tag is one of the supported
# languages, across region variants (es-US, es-ES, pt-BR, pt-PT, en-US, ...).
_REGIONS = ["US", "ES", "BR", "PT", "GB", "419", "MX", ""]


@st.composite
def supported_language_codes(draw: st.DrawFn) -> str:
    """A java.util.Locale code whose language sub-tag is es / pt / en."""
    lang = draw(st.sampled_from(["es", "pt", "en"]))
    region = draw(st.sampled_from(_REGIONS))
    sep = draw(st.sampled_from(["-", "_"]))
    code = lang if region == "" else f"{lang}{sep}{region}"
    # Optionally pad with surrounding whitespace (the router strips it).
    lead = draw(st.text(alphabet=" \t", max_size=2))
    trail = draw(st.text(alphabet=" \t", max_size=2))
    return lead + code + trail


# Arbitrary unknown values: unrecognized locale codes (fr-FR, ja-JP, ...),
# empty/whitespace, None, and non-str types. Filtered so none start with a
# supported sub-tag.
unknown_values = (
    st.one_of(
        st.text(),
        st.just(""),
        st.text(alphabet=" \t\n\r\f\v", min_size=0, max_size=5),
        st.sampled_from(["fr-FR", "ja-JP", "de-DE", "zh-CN", "it-IT", "ko-KR"]),
        st.none(),
        st.integers(),
        st.floats(allow_nan=True, allow_infinity=True),
        st.booleans(),
        st.lists(st.text()),
        st.dictionaries(st.text(), st.text()),
        st.binary(),
    )
    .filter(lambda v: _matched_prefix(v) is None)
)


@settings(max_examples=300)
@given(code=supported_language_codes())
def test_supported_locale_routes_to_that_language(code: str) -> None:
    """4.1/4.2/4.3: a supported $.LanguageCode sub-tag selects that path,
    regardless of the region variant."""
    selection = select_queue_experience(code)
    _assert_well_formed(selection)

    prefix = _matched_prefix(code)
    assert prefix is not None
    expected_language, expected_flow_key = _PREFIX_EXPECTED[prefix]
    assert selection.language == expected_language
    assert selection.flow_key == expected_flow_key
    assert selection.default_applied is False


@settings(max_examples=300)
@given(value=unknown_values)
def test_other_inputs_default_to_english(value: object) -> None:
    """4.4: absent/empty/unrecognized -> English path with default recorded."""
    selection = select_queue_experience(value)
    _assert_well_formed(selection)
    assert selection.language == ENGLISH
    assert selection.flow_key == "en"
    assert selection.default_applied is True


@settings(max_examples=300)
@given(value=st.one_of(supported_language_codes(), unknown_values))
def test_selection_is_total_and_well_formed(value: object) -> None:
    """4.5: never raises; always exactly one well-formed selection (en/es/pt)."""
    selection = select_queue_experience(value)
    _assert_well_formed(selection)
