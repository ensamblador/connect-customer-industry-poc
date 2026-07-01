"""Pure language-selection helper for the Localized Customer-queue flow.

This module is the testable realization of the internal language branch inside
the single Localized_Queue_Flow. It maps a contact's ``$.LanguageCode`` (the
Connect system attribute, a ``java.util.Locale`` string such as ``es-US``,
``pt-BR``, or ``en-US``) to exactly one internal path (Spanish / Portuguese /
English), defaulting to the English path whenever the value is absent, empty,
or unrecognized.

It mirrors the runtime ``Compare`` block inside the flow, which branches on
``$.LanguageCode`` using ``TextStartsWith`` on the language sub-tag (``es`` /
``pt`` / ``en``) so any region variant (``es-US``, ``es-ES``, ...) matches the
right path. It performs no I/O and never raises, so it can be property-tested
independently of the contact-flow engine (Requirements 4.1-4.5).
"""

from __future__ import annotations

from dataclasses import dataclass

# Canonical supported languages (the only non-default matches).
ENGLISH = "English"
SPANISH = "Spanish"
PORTUGUESE = "Portuguese"

# Internal flow path keys, one per language path inside the Localized_Queue_Flow.
_FLOW_KEY_EN = "en"
_FLOW_KEY_ES = "es"
_FLOW_KEY_PT = "pt"


@dataclass(frozen=True)
class QueueSelection:
    """The outcome of routing a contact to one internal queue-flow path.

    Attributes:
        language: The canonical language chosen ("English", "Spanish", or
            "Portuguese").
        flow_key: The internal path key, one of "es", "pt", or "en".
        default_applied: ``True`` when the English fallback was applied because
            the language code was absent, empty, or unrecognized (Requirement
            4.4).
    """

    language: str
    flow_key: str
    default_applied: bool


# Language sub-tag prefix -> selection, evaluated in order (mirrors the flow's
# TextStartsWith conditions: es, then pt, then en).
_PREFIX_MATCHES = (
    ("es", QueueSelection(SPANISH, _FLOW_KEY_ES, False)),
    ("pt", QueueSelection(PORTUGUESE, _FLOW_KEY_PT, False)),
    ("en", QueueSelection(ENGLISH, _FLOW_KEY_EN, False)),
)

# The default / no-match path: English, with default_applied recorded as True.
_DEFAULT_SELECTION = QueueSelection(ENGLISH, _FLOW_KEY_EN, True)


def select_queue_experience(language_code: object) -> QueueSelection:
    """Select exactly one internal queue-flow path for a contact.

    Matches ``language_code`` (the ``$.LanguageCode`` system attribute, e.g.
    ``es-US``) by its language sub-tag prefix — ``es`` -> Spanish, ``pt`` ->
    Portuguese, ``en`` -> English — mirroring the flow's ``TextStartsWith``
    conditions, so every region variant routes to the right path. Any other
    value -- including ``None``, a non-string, an empty/whitespace-only string,
    or an unrecognized code -- routes to the English path with
    ``default_applied=True``.

    This function never raises for any input (Requirement 4.5).

    Args:
        language_code: The contact's ``$.LanguageCode`` value, of any type.

    Returns:
        A :class:`QueueSelection` naming the chosen language, its internal
        ``flow_key`` (always one of "en"/"es"/"pt"), and whether the default
        was applied.
    """
    if isinstance(language_code, str):
        code = language_code.strip()
        for prefix, selection in _PREFIX_MATCHES:
            if code.startswith(prefix):
                return selection
    return _DEFAULT_SELECTION
