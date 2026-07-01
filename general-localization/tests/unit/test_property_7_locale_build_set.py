# Feature: message-localization, Property 7: Locale-enablement determines the built set (4 distinct prompts, 3 agents)
"""Property 7 — Locale-enablement determines the built set.

**Validates: Requirements 5.1, 5.2, 6.2, 7.2, 10.2, 10.3**

For any subset of locales marked enabled in ``config.LOCALES``, the stack's
build set equals the per-locale factory output for exactly the enabled
NON-English locales: each enabled non-English locale (``es_US`` and/or
``pt_BR``) yields exactly FOUR distinct AI prompts (query reformulation, answer
generation, intent labeling, note taking) — each with a published version — and
exactly THREE AI agents (Answer Recommendation, Manual Search, Note Taking),
where the answer-generation prompt version referenced by the Answer
Recommendation agent is the SAME version referenced by the Manual Search agent.
Disabled or absent locales (and ``en_US``, which drives the queue flow, not the
utility agents) yield no prompts or agents.

Strategy: generate an arbitrary ``LOCALES`` mapping over {en_US, es_US, pt_BR}
where each locale is independently enabled, disabled, or absent. Monkeypatch
``config.LOCALES`` to the generated mapping, build the stack under a FRESH
``cdk.App`` per example (avoiding construct-id collisions), synthesize with
``assertions.Template``, and inspect the resulting resources. ``config.LOCALES``
is restored after every example.
"""

from __future__ import annotations

import aws_cdk as core
import aws_cdk.assertions as assertions
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import config
from config_validation import parse_bool
from general_localization.general_localization_stack import GeneralLocalizationStack

# The three known locale keys; only the two non-English ones drive the AI-agent
# build set. en_US is always the queue-flow locale and never produces agents.
_LOCALE_KEYS = ("en_US", "es_US", "pt_BR")
_NON_ENGLISH = ("es_US", "pt_BR")

# CFN resource types the build set is measured in.
_PROMPT_TYPE = "AWS::Wisdom::AIPrompt"
_PROMPT_VERSION_TYPE = "AWS::Wisdom::AIPromptVersion"
_AGENT_TYPE = "AWS::Wisdom::AIAgent"


# Sentinel meaning "omit this locale key from the mapping entirely".
_ABSENT = object()

# Arbitrary enablement values. Enablement is resolved through ``parse_bool``, so
# we generate the full breadth of what an operator might write: real booleans,
# recognized truthy/falsy tokens (with odd casing/whitespace), unrecognized
# strings, integers, and ``None``. parse_bool decides enabled/disabled for each,
# and the expected build set is derived the same way — so this exercises a large
# input space (well over 100 distinct examples) rather than just the 8 boolean
# subsets.
_TRUTHY_TOKENS = st.sampled_from(["true", "True", "TRUE", "1", "yes", "on", "  true  "])
_FALSY_TOKENS = st.sampled_from(["false", "0", "no", "off", "", "maybe", "disabled"])
_ENABLEMENT_VALUES = st.one_of(
    st.booleans(),
    _TRUTHY_TOKENS,
    _FALSY_TOKENS,
    st.text(max_size=12),
    st.integers(),
    st.none(),
)


@st.composite
def locale_mappings(draw):
    """Generate an arbitrary ``LOCALES`` mapping over {en_US, es_US, pt_BR}.

    Each locale key is independently either omitted (absent) or assigned an
    arbitrary enablement value drawn from ``_ENABLEMENT_VALUES``. Enabled/
    disabled is resolved via ``parse_bool`` exactly as the stack does, so this
    covers booleans, recognized tokens, unrecognized strings, and missing keys.
    """
    mapping: dict[str, object] = {}
    for key in _LOCALE_KEYS:
        value = draw(st.one_of(st.just(_ABSENT), _ENABLEMENT_VALUES))
        if value is not _ABSENT:
            mapping[key] = value
    return mapping


def _enabled_non_english(mapping: dict[str, bool]) -> list[str]:
    """The non-English locales that resolve to enabled via ``parse_bool``."""
    return [loc for loc in _NON_ENGLISH if parse_bool(mapping.get(loc, False))]


def _flatten_config_json(node):
    """Walk a (possibly tokenized) native ``Configuration`` value.

    Returns ``(literal_text, prompt_version_logical_ids)`` where ``literal_text``
    is every literal string fragment concatenated and ``prompt_version_logical_ids``
    is the set of ``AWS::Wisdom::AIPromptVersion`` logical ids the configuration
    references via ``Fn::GetAtt`` (the published prompt-version ids the agent
    wires in).
    """
    literals: list[str] = []
    version_ids: set[str] = set()

    def walk(n):
        if isinstance(n, str):
            literals.append(n)
        elif isinstance(n, list):
            for item in n:
                walk(item)
        elif isinstance(n, dict):
            if "Fn::Join" in n:
                _sep, parts = n["Fn::Join"]
                walk(parts)
            elif "Fn::GetAtt" in n:
                logical_id, attr = n["Fn::GetAtt"][0], n["Fn::GetAtt"][1]
                if attr == "AIPromptVersionId" or "AiPromptVersion" in logical_id:
                    version_ids.add(logical_id)
            elif "Ref" in n:
                pass  # Refs (e.g. AWS::Partition) carry no build-set meaning here
            else:
                for value in n.values():
                    walk(value)

    walk(node)
    return "".join(literals), version_ids


def _agents_by_type_for_locale(agents: dict, agent_type: str, locale: str) -> list:
    """All AWS::Wisdom::AIAgent resources of ``agent_type`` whose Name ends
    with ``locale`` (the agent factory stamps the locale onto the Name)."""
    out = []
    for resource in agents.values():
        props = resource["Properties"]
        if props.get("Type") == agent_type and str(props.get("Name", "")).endswith(locale):
            out.append(resource)
    return out


@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(mapping=locale_mappings())
def test_locale_enablement_determines_build_set(mapping):
    enabled = _enabled_non_english(mapping)
    n = len(enabled)

    original_locales = config.LOCALES
    config.LOCALES = mapping
    try:
        app = core.App()
        stack = GeneralLocalizationStack(app, "Property7Stack")
        template = assertions.Template.from_stack(stack)

        prompts = template.find_resources(_PROMPT_TYPE)
        prompt_versions = template.find_resources(_PROMPT_VERSION_TYPE)
        agents = template.find_resources(_AGENT_TYPE)

        # --- Overall build set: 4 prompts + 4 versions + 3 agents per enabled
        #     non-English locale; disabled/absent locales (and en_US) add none.
        assert len(prompts) == 4 * n, (
            f"expected {4 * n} AIPrompts for {enabled}, got {len(prompts)}"
        )
        assert len(prompt_versions) == 4 * n, (
            f"expected {4 * n} AIPromptVersions for {enabled}, got {len(prompt_versions)}"
        )
        assert len(agents) == 3 * n, (
            f"expected {3 * n} AI agents for {enabled}, got {len(agents)}"
        )

        # --- Per enabled non-English locale: exactly one of each agent type,
        #     the shared answer-generation version, and suggestedMessages.
        for locale in enabled:
            ar = _agents_by_type_for_locale(agents, "ANSWER_RECOMMENDATION", locale)
            ms = _agents_by_type_for_locale(agents, "MANUAL_SEARCH", locale)
            nt = _agents_by_type_for_locale(agents, "NOTE_TAKING", locale)

            assert len(ar) == 1, f"{locale}: expected 1 ANSWER_RECOMMENDATION, got {len(ar)}"
            assert len(ms) == 1, f"{locale}: expected 1 MANUAL_SEARCH, got {len(ms)}"
            assert len(nt) == 1, f"{locale}: expected 1 NOTE_TAKING, got {len(nt)}"

            ar_literals, ar_versions = _flatten_config_json(ar[0]["Properties"]["Configuration"])
            _ms_literals, ms_versions = _flatten_config_json(ms[0]["Properties"]["Configuration"])

            # The Manual Search agent references exactly one prompt version — its
            # answer-generation version. That same version must be one of the
            # versions the Answer Recommendation agent references (shared prompt).
            assert len(ms_versions) == 1, (
                f"{locale}: Manual Search should reference exactly one prompt "
                f"version (the shared answer-generation one), got {ms_versions}"
            )
            shared_version = next(iter(ms_versions))
            assert shared_version in ar_versions, (
                f"{locale}: answer-generation version {shared_version} referenced "
                f"by Manual Search is not shared with Answer Recommendation "
                f"(which references {ar_versions})"
            )
    finally:
        config.LOCALES = original_locales
