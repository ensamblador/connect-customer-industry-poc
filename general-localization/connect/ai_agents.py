"""
connect/ai_agents.py — localized Q in Connect utility prompt + agent factory.

This module is the realization of Deliverable 2 (localized utility AI agents),
built entirely on native CDK L1 constructs (``CfnAIPrompt`` /
``CfnAIPromptVersion`` / ``CfnAIAgent`` / ``CfnAIAgentVersion``) — no boto3
custom resource is used. The telco-cx project proved the native
``AWS::Wisdom::AIAgent`` path works for Q in Connect agents: the empty
``outputFilters: []`` the managed provider injects is benign, and the only
real failure mode (a stringified ``maxLength`` inside a tool ``inputSchema``)
does not apply here because these utility agents carry no tool configurations.

It is split into three concerns, in build order:

  1. ``build_ai_prompt`` — builds the native L1 ``CfnAIPrompt`` ->
     ``CfnAIPromptVersion`` chain under the assistant for one locale and body,
     returning the prompt construct (for ARN outputs) and its published version
     id (referenced by the agents). Mirrors the telco-cx ``CfnAIPrompt`` /
     ``CfnAIPromptVersion`` convention.

  2. ``build_localized_prompts`` — the four-prompt builder. For a given locale
     it builds the FOUR distinct prompts exactly once — query reformulation,
     answer generation, intent labeling, note taking — and publishes a version
     of each. The single answer-generation prompt version is reused by BOTH the
     Answer Recommendation and the Manual Search agents (no duplicate
     answer-generation prompt), satisfying Requirements 5.1, 5.2, 6.2 and 7.2.

  3. ``LocalizedUtilityAIAgent`` + the three locale-parameterized agent builders
     (``build_answer_recommendation_agent`` / ``build_manual_search_agent`` /
     ``build_note_taking_agent``). Each builder assembles the type-specific
     native ``AIAgentConfigurationProperty`` and creates one ``CfnAIAgent`` (+ a
     published ``CfnAIAgentVersion``) under the assistant, wiring the published
     prompt versions from ``build_localized_prompts``.

Note on ``suggestedMessages``: the Q in Connect API accepts a
``suggestedMessages`` array on the ANSWER_RECOMMENDATION configuration, but the
CloudFormation ``AWS::Wisdom::AIAgent`` resource does NOT expose that property,
so it is not set on the native path. If the quick-reply suggestions are needed,
re-introduce them via a thin custom resource scoped to that single agent.

Requirements: 5.1, 5.2, 5.3, 5.4, 5.6, 5.7.
"""

from __future__ import annotations

import hashlib
import os
from typing import NamedTuple

from aws_cdk import aws_wisdom as wisdom
from constructs import Construct

import config


# Directory holding the AI prompt template bodies, read out of band from the
# reference Q in Connect prompts (with a source profile) and committed to the
# repo verbatim. Synthesis loads them from disk and performs no AWS call.
_PROMPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts"
)

# --------------------------------------------------------------------------- #
# Defaults for build_ai_prompt. The AWS::Wisdom::AIPrompt TemplateType is always
# TEXT; api format and model id vary per prompt type (see PROMPT_SPECS) and are
# passed explicitly, so these are only fallbacks for ad-hoc callers.
# --------------------------------------------------------------------------- #
DEFAULT_API_FORMAT = "MESSAGES"
DEFAULT_TEMPLATE_TYPE = "TEXT"

# AI agent type constants (consumed by the agent builders).
AGENT_TYPE_ANSWER_RECOMMENDATION = "ANSWER_RECOMMENDATION"
AGENT_TYPE_MANUAL_SEARCH = "MANUAL_SEARCH"
AGENT_TYPE_NOTE_TAKING = "NOTE_TAKING"

# The four distinct prompt sources, keyed by the design's AiPromptModel.source
# values. ``answer_generation`` is the SHARED prompt referenced by both the
# Answer Recommendation and the Manual Search agents (Requirements 5.1, 5.2).
SOURCE_QUERY_REFORMULATION = "query_reformulation"
SOURCE_ANSWER_GENERATION = "answer_generation"
SOURCE_INTENT_LABELING = "intent_labeling"
SOURCE_NOTE_TAKING = "note_taking"


class _PromptSpec(NamedTuple):
    """Static metadata for one of the four prompt sources.

    ``prompt_type``, ``api_format``, and ``model_id`` mirror the reference Q in
    Connect prompts EXACTLY — QConnect rejects a mismatched api format for a
    given prompt type (e.g. ANSWER_GENERATION requires TEXT_COMPLETIONS, not
    MESSAGES). ``body_file`` is the committed template file under ``prompts/``.
    """

    prompt_type: str       # AWS::Wisdom::AIPrompt Type enum value
    name_suffix: str       # human-readable suffix used in the AI prompt name
    api_format: str        # AWS::Wisdom::AIPrompt ApiFormat (per prompt type)
    model_id: str          # the model the reference prompt was authored against
    body_file: str         # template file under prompts/ (loaded verbatim)


# Map each prompt source to its AI prompt Type, name suffix, api format, model
# id, and template file. The api format + model id are taken verbatim from the
# reference prompts in the source account so CreateAIPrompt validation passes.
PROMPT_SPECS: dict[str, _PromptSpec] = {
    SOURCE_QUERY_REFORMULATION: _PromptSpec(
        prompt_type="QUERY_REFORMULATION",
        name_suffix="query-reformulation",
        api_format="MESSAGES",
        model_id="us.amazon.nova-lite-v1:0",
        body_file="query_reformulation.yaml",
    ),
    SOURCE_ANSWER_GENERATION: _PromptSpec(
        prompt_type="ANSWER_GENERATION",
        name_suffix="answer-generation",
        # ANSWER_GENERATION only supports TEXT_COMPLETIONS (not MESSAGES).
        api_format="TEXT_COMPLETIONS",
        model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        body_file="answer_generation.yaml",
    ),
    SOURCE_INTENT_LABELING: _PromptSpec(
        prompt_type="INTENT_LABELING_GENERATION",
        name_suffix="intent-labeling",
        api_format="MESSAGES",
        model_id="us.amazon.nova-pro-v1:0",
        body_file="intent_labeling.yaml",
    ),
    SOURCE_NOTE_TAKING: _PromptSpec(
        prompt_type="NOTE_TAKING",
        name_suffix="note-taking",
        api_format="MESSAGES",
        model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        body_file="note_taking.yaml",
    ),
}


class BuiltPrompt(NamedTuple):
    """The result of building one localized prompt.

    Supports both tuple unpacking ``prompt, version_id = built[source]`` and
    attribute access ``built[source].version_id`` / ``built[source].prompt``.
    ``prompt`` exposes ``.attr_ai_prompt_arn`` for the Req 11 ARN outputs;
    ``version_id`` is the published version id the agents reference (Req 5.7).
    """

    prompt: wisdom.CfnAIPrompt
    version_id: str


# --------------------------------------------------------------------------- #
# AI prompt L1 chain builder (CfnAIPrompt -> CfnAIPromptVersion).
# --------------------------------------------------------------------------- #
def build_ai_prompt(
    scope: Construct,
    *,
    assistant_id: str,
    name: str,
    locale: str,
    body: str,
    model_id: str,
    prompt_type: str,
    api_format: str = DEFAULT_API_FORMAT,
    template_type: str = DEFAULT_TEMPLATE_TYPE,
) -> BuiltPrompt:
    """Build a ``CfnAIPrompt`` -> ``CfnAIPromptVersion`` chain under the
    assistant for one locale and body.

    Creates the AI prompt (Req 5.3 — under the Q_Assistant) with the given
    localized ``body`` (Req 5.5), then publishes a version (Req 5.7) whose id the
    AI agents reference. Returns a :class:`BuiltPrompt` (``prompt``, ``version_id``).

    Note: ``prompt_type`` (AWS::Wisdom::AIPrompt ``Type``) and ``template_type``
    (always ``TEXT``) are required by the L1 resource; they extend the design's
    headline signature so each of the four prompt sources can carry its own
    distinct Type.
    """
    base_id = _construct_id_fragment(name)

    prompt = wisdom.CfnAIPrompt(
        scope,
        f"AiPrompt{base_id}",
        assistant_id=assistant_id,
        name=name,
        type=prompt_type,
        api_format=api_format,
        model_id=model_id,
        template_type=template_type,
        description=f"Localized {prompt_type} prompt ({locale}).",
        template_configuration=wisdom.CfnAIPrompt.AIPromptTemplateConfigurationProperty(
            text_full_ai_prompt_edit_template_configuration=(
                wisdom.CfnAIPrompt.TextFullAIPromptEditTemplateConfigurationProperty(
                    text=body,
                )
            )
        ),
    )

    # The version construct id embeds a content hash so it is immutable per
    # body/locale (a new body publishes a new version), matching telco-cx.
    version = wisdom.CfnAIPromptVersion(
        scope,
        f"AiPromptVersion{base_id}{_content_hash(body, locale, model_id)}",
        assistant_id=assistant_id,
        ai_prompt_id=prompt.attr_ai_prompt_id,
    )

    return BuiltPrompt(prompt=prompt, version_id=version.attr_ai_prompt_version_id)


# --------------------------------------------------------------------------- #
# Four-prompt builder — builds all four distinct prompts once per locale, with
# the answer-generation prompt published once and reused by two agents.
# --------------------------------------------------------------------------- #
def build_localized_prompts(
    scope: Construct,
    *,
    locale: str,
    assistant_id: str | None = None,
) -> dict[str, BuiltPrompt]:
    """Build the FOUR distinct localized AI prompts for ``locale`` and publish a
    version of each (Requirements 5.1, 5.3, 5.4, 5.7).

    Returns a dict mapping each prompt source to its :class:`BuiltPrompt`::

        {
            "query_reformulation": BuiltPrompt(prompt=..., version_id=...),
            "answer_generation":   BuiltPrompt(prompt=..., version_id=...),  # SHARED
            "intent_labeling":     BuiltPrompt(prompt=..., version_id=...),
            "note_taking":         BuiltPrompt(prompt=..., version_id=...),
        }

    Each prompt's body is loaded verbatim from the committed template file under
    ``prompts/`` and created with the api format + model id the reference prompt
    was authored against (QConnect rejects a mismatched api format for a given
    type). The ``answer_generation`` entry is built once; its ``version_id`` is
    the single shared value the agent builders pass to BOTH the Answer
    Recommendation and the Manual Search agents (Requirements 5.2, 6.2, 7.2), so
    the shared prompt is referenced twice without being recreated.
    """
    assistant_id = assistant_id or config.ASSISTANT_ID

    built: dict[str, BuiltPrompt] = {}
    for source, spec in PROMPT_SPECS.items():
        built[source] = build_ai_prompt(
            scope,
            assistant_id=assistant_id,
            name=f"localized-{spec.name_suffix}-{locale}",
            locale=locale,
            body=_load_prompt_body(spec.body_file),
            api_format=spec.api_format,
            model_id=spec.model_id,
            prompt_type=spec.prompt_type,
        )
    return built


# --------------------------------------------------------------------------- #
# Prompt-body loading. Bodies are read verbatim from the reference prompt
# templates committed under ``prompts/`` (Req 5.5). They are locale-agnostic —
# language is driven at runtime by the ``{{$.locale}}`` template variable and
# the agent's ``locale`` setting — so one template serves every Target_Locale.
# Synthesis performs no AWS call; the templates are static repo files.
# --------------------------------------------------------------------------- #
def _load_prompt_body(body_file: str) -> str:
    """Load a committed AI prompt template body verbatim from ``prompts/``."""
    path = os.path.join(_PROMPTS_DIR, body_file)
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


# --------------------------------------------------------------------------- #
# Construct-id helpers.
# --------------------------------------------------------------------------- #
def _construct_id_fragment(name: str) -> str:
    """Turn an AI prompt name into an alphanumeric CamelCase construct-id
    fragment (e.g. ``localized-answer-generation-es_US`` -> ``LocalizedAnswerGenerationEsUS``)."""
    return "".join(part for part in name.replace("_", "-").title().split("-") if part)


def _content_hash(*parts: str) -> str:
    """Short stable hash for the immutable CfnAIPromptVersion construct id."""
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return digest[:10]


# --------------------------------------------------------------------------- #
# Native AI agent construct (CfnAIAgent -> CfnAIAgentVersion).
# --------------------------------------------------------------------------- #
class LocalizedUtilityAIAgent(Construct):
    """One localized Q in Connect utility AI agent, native L1.

    Creates a ``CfnAIAgent`` for the given type-specific configuration and a
    published ``CfnAIAgentVersion`` under it (preserving the published-version
    semantics the previous custom-resource implementation provided). Exposes the
    same ``ai_agent_id`` / ``ai_agent_arn`` / ``ai_agent_qualified_id`` /
    ``ai_agent_version_arn`` properties the previous ``AiAgentResource`` did, so
    callers (outputs / SSM parameters) need no change.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        assistant_id: str,
        name: str,
        agent_type: str,
        configuration: "wisdom.CfnAIAgent.AIAgentConfigurationProperty",
        description: str = "",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self._agent = wisdom.CfnAIAgent(
            self,
            "Agent",
            assistant_id=assistant_id,
            name=name,
            type=agent_type,
            description=description or "",
            configuration=configuration,
        )
        # Publish an immutable version of the agent (mirrors the prompts' chain
        # and the previous custom resource, which minted a version on create).
        self._version = wisdom.CfnAIAgentVersion(
            self,
            "Version",
            assistant_id=assistant_id,
            ai_agent_id=self._agent.attr_ai_agent_id,
        )

    @property
    def ai_agent_id(self) -> str:
        return self._agent.attr_ai_agent_id

    @property
    def ai_agent_arn(self) -> str:
        return self._agent.attr_ai_agent_arn

    @property
    def ai_agent_qualified_id(self) -> str:
        # "<agentId>:<version>" — the freshly published version.
        return self._version.attr_ai_agent_version_id

    @property
    def ai_agent_version_arn(self) -> str:
        return self._version.attr_ai_agent_arn


# --------------------------------------------------------------------------- #
# Locale-parameterized agent builders.
#
# Each builder assembles the type-specific native ``AIAgentConfigurationProperty``
# and creates one ``LocalizedUtilityAIAgent`` under the assistant. The four
# prompt versions come from ``build_localized_prompts``; the single
# answer-generation version is passed to BOTH the Answer Recommendation and the
# Manual Search agents so the shared prompt is referenced twice without being
# recreated (Requirements 5.2, 6.2, 7.2).
#
# Locale resolution: every agent defaults to the active ``locale`` passed in,
# unless ``config.AGENT_LOCALE_OVERRIDES`` pins that agent type to a different
# locale (keyed by the agent-type string, e.g. "ANSWER_RECOMMENDATION").
#
# A required prompt-version id that is None/empty raises ValueError naming the
# missing prompt, leaving no agent created (Requirements 6.6, 7.5, 8.5).
# Requirements: 6.1, 6.2, 6.3, 7.1, 7.2, 7.3, 8.1, 8.2, 8.3, 5.5, 6.6, 7.5, 8.5.
# --------------------------------------------------------------------------- #
def _resolve_agent_locale(agent_type: str, locale: str) -> str:
    """Return the locale for ``agent_type``: a ``config.AGENT_LOCALE_OVERRIDES``
    entry when present, otherwise the active ``locale`` passed in."""
    return config.AGENT_LOCALE_OVERRIDES.get(agent_type, locale)


def _require_prompt_version(name: str, value: str | None) -> str:
    """Return ``value`` when it is a usable prompt-version id, else raise
    ValueError naming the missing prompt (Requirements 6.6, 7.5, 8.5)."""
    if value is None or (isinstance(value, str) and value.strip() == ""):
        raise ValueError(
            f"Required AI prompt version '{name}' is unavailable (None/empty); "
            "cannot build the AI agent that references it."
        )
    return value


def build_answer_recommendation_agent(
    scope: Construct,
    *,
    locale: str,
    query_reformulation_prompt_version: str,
    answer_generation_prompt_version: str,
    intent_labeling_prompt_version: str,
    assistant_id: str | None = None,
) -> LocalizedUtilityAIAgent:
    """Build the ANSWER_RECOMMENDATION agent (Requirements 6.1-6.4).

    References all three prompt versions — query reformulation, the SHARED
    answer-generation version, and intent labeling. Raises naming the missing
    prompt if any required version is unavailable (Req 6.6).

    Note: ``suggestedMessages`` is not set — the CloudFormation
    ``AWS::Wisdom::AIAgent`` resource does not expose that property (see the
    module docstring).
    """
    assistant_id = assistant_id or config.ASSISTANT_ID
    agent_locale = _resolve_agent_locale(AGENT_TYPE_ANSWER_RECOMMENDATION, locale)

    configuration = wisdom.CfnAIAgent.AIAgentConfigurationProperty(
        answer_recommendation_ai_agent_configuration=(
            wisdom.CfnAIAgent.AnswerRecommendationAIAgentConfigurationProperty(
                query_reformulation_ai_prompt_id=_require_prompt_version(
                    "query_reformulation", query_reformulation_prompt_version
                ),
                answer_generation_ai_prompt_id=_require_prompt_version(
                    "answer_generation", answer_generation_prompt_version
                ),
                intent_labeling_generation_ai_prompt_id=_require_prompt_version(
                    "intent_labeling", intent_labeling_prompt_version
                ),
                locale=agent_locale,
            )
        )
    )

    return LocalizedUtilityAIAgent(
        scope,
        f"AiAgentAnswerRecommendation{_construct_id_fragment(agent_locale)}",
        assistant_id=assistant_id,
        name=f"localized-answer-recommendation-{agent_locale}",
        agent_type=AGENT_TYPE_ANSWER_RECOMMENDATION,
        configuration=configuration,
        description=f"Localized Answer Recommendation agent ({agent_locale}).",
    )


def build_manual_search_agent(
    scope: Construct,
    *,
    locale: str,
    answer_generation_prompt_version: str,
    assistant_id: str | None = None,
) -> LocalizedUtilityAIAgent:
    """Build the MANUAL_SEARCH agent (Requirements 7.1-7.3).

    References the SAME shared answer-generation version that the Answer
    Recommendation agent uses, as its ``answerGenerationAIPromptId``. Raises
    naming the missing prompt if the version is unavailable (Req 7.5).
    """
    assistant_id = assistant_id or config.ASSISTANT_ID
    agent_locale = _resolve_agent_locale(AGENT_TYPE_MANUAL_SEARCH, locale)

    configuration = wisdom.CfnAIAgent.AIAgentConfigurationProperty(
        manual_search_ai_agent_configuration=(
            wisdom.CfnAIAgent.ManualSearchAIAgentConfigurationProperty(
                answer_generation_ai_prompt_id=_require_prompt_version(
                    "answer_generation", answer_generation_prompt_version
                ),
                locale=agent_locale,
            )
        )
    )

    return LocalizedUtilityAIAgent(
        scope,
        f"AiAgentManualSearch{_construct_id_fragment(agent_locale)}",
        assistant_id=assistant_id,
        name=f"localized-manual-search-{agent_locale}",
        agent_type=AGENT_TYPE_MANUAL_SEARCH,
        configuration=configuration,
        description=f"Localized Manual Search agent ({agent_locale}).",
    )


def build_note_taking_agent(
    scope: Construct,
    *,
    locale: str,
    note_taking_prompt_version: str,
    assistant_id: str | None = None,
) -> LocalizedUtilityAIAgent:
    """Build the NOTE_TAKING agent (Requirements 8.1-8.3).

    Wires its single note-taking prompt version as
    ``noteTakingAIAgentConfiguration.noteTakingAIPromptId``. Raises naming the
    missing prompt if the version is unavailable (Req 8.5).
    """
    assistant_id = assistant_id or config.ASSISTANT_ID
    agent_locale = _resolve_agent_locale(AGENT_TYPE_NOTE_TAKING, locale)

    configuration = wisdom.CfnAIAgent.AIAgentConfigurationProperty(
        note_taking_ai_agent_configuration=(
            wisdom.CfnAIAgent.NoteTakingAIAgentConfigurationProperty(
                note_taking_ai_prompt_id=_require_prompt_version(
                    "note_taking", note_taking_prompt_version
                ),
                locale=agent_locale,
            )
        )
    )

    return LocalizedUtilityAIAgent(
        scope,
        f"AiAgentNoteTaking{_construct_id_fragment(agent_locale)}",
        assistant_id=assistant_id,
        name=f"localized-note-taking-{agent_locale}",
        agent_type=AGENT_TYPE_NOTE_TAKING,
        configuration=configuration,
        description=f"Localized Note Taking agent ({agent_locale}).",
    )
