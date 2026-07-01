# Feature: message-localization, Property 8: Outputs correspond exactly to created resources
"""Property-based test for ``GeneralLocalizationStack._create_outputs``.

Property 8: Outputs correspond exactly to created resources.

*For any* configuration of enabled locales and queue-flow creation, the set of
resource-ARN stack outputs corresponds one-to-one with the set of resources the
stack actually creates -- the single created Localized_Queue_Flow has exactly
one ``QueueFlowArn`` output, every created prompt (four per enabled non-English
locale) and agent (three per enabled non-English locale) has exactly one ARN
output, and no output references a resource that was not created.

**Validates: Requirements 11.5**

Strategy: generate enabled / disabled / absent subsets of the three locales
{en_US, es_US, pt_BR}, monkeypatch ``config.LOCALES`` to that subset, instantiate
``GeneralLocalizationStack`` under a FRESH ``cdk.App`` per example (a unique
construct tree each time, so the singleton AI-agent provider never collides),
and enumerate the synthesized template's ``Outputs`` via
``aws_cdk.assertions.Template``. We then assert the set of output logical names
is exactly the set derived one-to-one from the stack's actually-created
resources (``self._queue_flow`` + ``self._ai_prompts`` + ``self._ai_agents``).
``config.LOCALES`` is restored after every example.
"""

from __future__ import annotations

import aws_cdk as cdk
import aws_cdk.assertions as assertions
from hypothesis import given, settings
from hypothesis import strategies as st

import config
from config_validation import parse_bool
from general_localization.general_localization_stack import (
    GeneralLocalizationStack,
    _AGENT_TYPE_TOKENS,
    _PROMPT_SOURCE_TOKENS,
    _locale_token,
)

# The three locales the stack knows about. ``en_US`` always drives the queue
# experience (Deliverable 1) but never a utility prompt/agent set, so the
# AI-agent rollout covers only the enabled NON-English locales.
_LOCALE_KEYS = ["en_US", "es_US", "pt_BR"]


@st.composite
def _locales_configs(draw):
    """Generate an arbitrary enabled / disabled / absent subset of the three
    locales as a ``config.LOCALES``-shaped dict.

    Each locale is independently set to ``True`` (enabled), ``False``
    (disabled), or omitted entirely (absent -> disabled via ``parse_bool``).
    This exercises every enablement combination, including the empty config
    (only the always-on queue flow) and the all-enabled config.
    """
    cfg: dict[str, bool] = {}
    for key in _LOCALE_KEYS:
        choice = draw(st.sampled_from(["enabled", "disabled", "absent"]))
        if choice == "enabled":
            cfg[key] = True
        elif choice == "disabled":
            cfg[key] = False
        # "absent": leave the key out of the dict entirely
    return cfg


def _expected_output_names(stack: GeneralLocalizationStack) -> set[str]:
    """Derive the expected set of output logical names from the resources the
    stack ACTUALLY created, establishing the one-to-one correspondence.

    One ``QueueFlowArn`` for the always-created queue flow, one
    ``AiPrompt<Source><Locale>Arn`` per created prompt, and one
    ``AiAgent<Type><Locale>Arn`` per created agent.
    """
    expected = {"QueueFlowArn", "InitFlowModuleArn"}
    for locale, prompts in stack._ai_prompts.items():
        locale_token = _locale_token(locale)
        for source in prompts:
            expected.add(f"AiPrompt{_PROMPT_SOURCE_TOKENS[source]}{locale_token}Arn")
    for locale, agents in stack._ai_agents.items():
        locale_token = _locale_token(locale)
        for agent_type in agents:
            expected.add(f"AiAgent{_AGENT_TYPE_TOKENS[agent_type]}{locale_token}Arn")
    return expected


@settings(max_examples=100, deadline=None)
@given(locales=_locales_configs())
def test_outputs_correspond_one_to_one_with_created_resources(locales):
    """The synthesized outputs are one-to-one with the created resources."""
    original_locales = config.LOCALES
    config.LOCALES = locales
    try:
        # Fresh App per example so the per-stack singleton AI-agent provider
        # and every construct id are unique (no cross-example collisions).
        app = cdk.App()
        stack = GeneralLocalizationStack(app, "GeneralLocalization")
        template = assertions.Template.from_stack(stack)
        outputs = template.to_json().get("Outputs", {})
    finally:
        config.LOCALES = original_locales

    actual_names = set(outputs.keys())

    # Number of enabled NON-English locales drives the prompt/agent counts.
    enabled_non_english = [
        locale
        for locale, flag in locales.items()
        if locale != "en_US" and parse_bool(flag)
    ]
    n = len(enabled_non_english)

    # 1) Total output count: 1 queue flow + 1 init flow module + 4 prompts +
    #    3 agents per enabled non-English locale.
    expected_count = 2 + 4 * n + 3 * n
    assert len(actual_names) == expected_count, (
        f"expected {expected_count} outputs for {n} enabled non-English "
        f"locale(s) {enabled_non_english}, got {len(actual_names)}: "
        f"{sorted(actual_names)}"
    )

    # 2) Exactly one QueueFlowArn output (the always-created queue flow).
    assert "QueueFlowArn" in actual_names
    assert sum(1 for name in actual_names if name == "QueueFlowArn") == 1

    # The init-flow-es-v2 module output is always present too.
    assert "InitFlowModuleArn" in actual_names

    # 3) One-to-one: the output names equal exactly the names derived from the
    #    resources the stack actually created (no missing, no extra).
    expected_names = _expected_output_names(stack)
    assert actual_names == expected_names, (
        "outputs do not correspond one-to-one with created resources.\n"
        f"  missing (created but no output): {sorted(expected_names - actual_names)}\n"
        f"  extra (output but not created):  {sorted(actual_names - expected_names)}"
    )

    # 4) Per-resource correspondence counts: each created prompt has exactly one
    #    AiPrompt*Arn output and each created agent exactly one AiAgent*Arn.
    created_prompt_count = sum(len(p) for p in stack._ai_prompts.values())
    created_agent_count = sum(len(a) for a in stack._ai_agents.values())
    assert created_prompt_count == 4 * n
    assert created_agent_count == 3 * n
    assert sum(1 for name in actual_names if name.startswith("AiPrompt")) == created_prompt_count
    assert sum(1 for name in actual_names if name.startswith("AiAgent")) == created_agent_count

    # 5) No output references an uncreated resource: a disabled/absent locale
    #    contributes no outputs carrying its token (e.g. no PtBr outputs when
    #    pt_BR is not an enabled non-English locale).
    for locale in _LOCALE_KEYS:
        if locale not in enabled_non_english:
            token = _locale_token(locale)
            stray = [name for name in actual_names if token in name and name != "QueueFlowArn"]
            assert not stray, (
                f"locale {locale} is not a built AI-agent locale yet produced "
                f"outputs: {stray}"
            )

    # 6) Every output value is a non-empty ARN reference (the full ARN string).
    for name, body in outputs.items():
        assert "Value" in body, f"output {name} has no Value"
        assert body["Value"], f"output {name} has an empty Value"


def test_pt_br_disabled_produces_no_portuguese_outputs():
    """Anchor example: the default config (es_US enabled, pt_BR disabled)
    yields the es_US set plus the queue flow and no Portuguese outputs."""
    original_locales = config.LOCALES
    config.LOCALES = {"en_US": True, "es_US": True, "pt_BR": False}
    try:
        app = cdk.App()
        stack = GeneralLocalizationStack(app, "GeneralLocalization")
        template = assertions.Template.from_stack(stack)
        outputs = template.to_json().get("Outputs", {})
    finally:
        config.LOCALES = original_locales

    names = set(outputs.keys())
    # 1 queue flow + 1 init flow module + 4 prompts + 3 agents for es_US only.
    assert len(names) == 2 + 4 + 3
    assert "QueueFlowArn" in names
    assert "InitFlowModuleArn" in names
    assert not [n for n in names if "PtBr" in n]
    assert all(
        "EsUs" in n
        for n in names
        if n not in ("QueueFlowArn", "InitFlowModuleArn")
    )
