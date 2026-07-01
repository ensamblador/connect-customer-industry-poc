"""GeneralLocalizationStack — composes the localized queue flow and the
per-locale Q in Connect AI prompts/agents.

The constructor runs fail-closed config resolution FIRST (``_resolve_config``)
so that a missing or blank required configuration value raises ``ConfigError``
before any construct is created — the stack then defines no resources
(Requirements 1.6, 1.7, 2.1, 2.2, 2.3, 3.6, 10.4).

The ``connect/`` package and the ``config`` / ``config_validation`` /
``language_router`` helper modules live at the project root, which is on
``sys.path`` when CDK runs ``app.py``; hence the bare ``import config`` /
``from config_validation import ...`` below.
"""

import json
import os

from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_ssm as ssm
from constructs import Construct

import config
from config_validation import (
    ConfigError,  # noqa: F401  (re-exported for callers/tests)
    parse_bool,
    require,
    require_hold_message,
)
from connect.flows import ContactFlow, ContactFlowModule
from connect.prompt_lookup_cr import PromptByName
from connect import ai_agents

# Repo root for projects/general-localization (the dir holding flows/, config.py,
# and the connect/ package). This file lives one package deeper, so go up two.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The single localized customer-queue Flow-language JSON authored in task 6.2.
_QUEUE_FLOW_PATH = os.path.join(
    _PROJECT_ROOT, "flows", "localized-customer-queue", "flow.json"
)

# Contact-flow name distinct from the live "Default Customer Queue" (Req 3.5).
_QUEUE_FLOW_NAME = "Localized Customer Queue"

# The init-flow-es contact flow module JSON, ported from the live instance
# module and extended with a "Set customer queue flow" block.
_INIT_FLOW_PATH = os.path.join(_PROJECT_ROOT, "flows", "init-es", "flow.json")

# Marker in the init-flow JSON resolved at synth to the localized queue flow ARN
# (the CustomerQueue event hook). Mirrors the telco-cx flow-marker convention.
_QUEUE_FLOW_ARN_MARKER = "QUEUE_FLOW_ARN_PLACEHOLDER"

# --------------------------------------------------------------------------- #
# Output logical-name token maps (Req 11.2, 11.3).
#
# CfnOutput logical ids must be alphanumeric and unique. We map each prompt
# source and each agent type to a readable CamelCase token, and render the
# locale (e.g. "es_US") to a CamelCase token (e.g. "EsUs") via _locale_token.
# --------------------------------------------------------------------------- #
_PROMPT_SOURCE_TOKENS = {
    ai_agents.SOURCE_QUERY_REFORMULATION: "QueryReformulation",
    ai_agents.SOURCE_ANSWER_GENERATION: "AnswerGeneration",
    ai_agents.SOURCE_INTENT_LABELING: "IntentLabeling",
    ai_agents.SOURCE_NOTE_TAKING: "NoteTaking",
}

_AGENT_TYPE_TOKENS = {
    ai_agents.AGENT_TYPE_ANSWER_RECOMMENDATION: "AnswerRecommendation",
    ai_agents.AGENT_TYPE_MANUAL_SEARCH: "ManualSearch",
    ai_agents.AGENT_TYPE_NOTE_TAKING: "NoteTaking",
}


def _locale_token(locale: str) -> str:
    """Render a locale id (e.g. ``es_US``) into a CamelCase logical-name token
    (e.g. ``EsUs``): split on ``_`` and capitalize each segment, so every
    character is alphanumeric and the result is unique per locale."""
    return "".join(segment.capitalize() for segment in locale.split("_") if segment)


class GeneralLocalizationStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Fail-closed FIRST: resolve/validate every mandatory config value
        # before any construct is created. A missing/blank value raises
        # ConfigError here, so the stack defines no resources.
        self._resolve_config()

        # Subsequent phases (added by tasks 10.2–10.4) consume the resolved
        # config stored on self by _resolve_config().
        self._create_queue_flow()
        self._create_init_flow_module()
        self._create_ai_prompts_and_agents()
        self._create_outputs()
        self._create_parameters()

    def _resolve_config(self) -> None:
        """Resolve and validate all mandatory configuration, fail-closed.

        Calls ``require`` for every mandatory scalar constant,
        ``require_hold_message`` for each per-language hold message, and
        ``parse_bool`` over ``config.LOCALES`` to resolve the enabled locales.
        Runs in full before any resource is defined, so the first absent value
        raises ``ConfigError`` (naming the constant/language) and the stack
        emits no template (Requirements 1.6, 1.7, 2.1, 2.2, 2.3, 3.6, 10.4).

        Stores the resolved values on ``self`` for downstream phases:
          - ``self._cfg``: dict of resolved scalar config values
          - ``self._hold_messages``: dict of resolved per-language hold texts
          - ``self._enabled_locales``: list of locales whose flag is truthy
        """
        # --- Mandatory scalar constants (require) ------------------------
        # Connect / Q in Connect identity.
        cfg: dict[str, str] = {
            "INSTANCE_ID": require("INSTANCE_ID", getattr(config, "INSTANCE_ID", None)),
            "ASSISTANT_ID": require("ASSISTANT_ID", getattr(config, "ASSISTANT_ID", None)),
        }

        # TTS voices + engine for the localized queue flow's per-language paths.
        tts_names = (
            "TTS_VOICE_EN",
            "TTS_VOICE_ES",
            "TTS_VOICE_PT",
            "TTS_ENGINE",
        )
        for name in tts_names:
            cfg[name] = require(name, getattr(config, name, None))

        # --- Per-language hold messages (require_hold_message) -----------
        # Naming the language; enforces non-blank + the 3000-char ceiling.
        hold_messages = {
            "en_US": require_hold_message("en_US", getattr(config, "HOLD_MESSAGE_EN", None)),
            "es_US": require_hold_message("es_US", getattr(config, "HOLD_MESSAGE_ES", None)),
            "pt_BR": require_hold_message("pt_BR", getattr(config, "HOLD_MESSAGE_PT", None)),
        }

        # --- Enabled locales (parse_bool over config.LOCALES) ------------
        locales = getattr(config, "LOCALES", {}) or {}
        enabled_locales = [
            locale for locale, flag in locales.items() if parse_bool(flag)
        ]

        # Store resolved values for downstream phases (10.2–10.4).
        self._cfg = cfg
        self._hold_messages = hold_messages
        self._enabled_locales = enabled_locales

    @staticmethod
    def _json_escape(value: str) -> str:
        """Escape a value for safe inline substitution into the flow JSON.

        The ``ContactFlow`` construct substitutes markers via raw ``str.replace``
        into the Flow-language JSON document. A hold message (or any value)
        containing a double quote, backslash, or control character would break
        the surrounding JSON string literal. ``json.dumps`` produces a fully
        escaped JSON string *with* its surrounding quotes; we strip those quotes
        (``[1:-1]``) because the marker already sits inside quotes in the
        template, leaving only the escaped interior.
        """
        return json.dumps(value)[1:-1]

    def _create_queue_flow(self) -> None:
        """Create the single localized customer-queue contact flow (Deliverable 1).

        Instantiates ONE ``ContactFlow`` of type ``CUSTOMER_QUEUE`` from the
        authored ``flows/localized-customer-queue/flow.json``, rendering all
        three languages' hold-message and TTS-voice markers from the resolved
        config. Each substituted value is JSON-escaped so the rendered document
        stays valid JSON. The flow is given a name distinct from the Default
        Customer Queue (Req 3.5).

        Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.1, 4.2, 4.3, 4.4.
        """
        # Defensive re-check (Req 3.6): _resolve_config already validated the
        # hold messages via require_hold_message, so this never fires in
        # practice — but it guarantees the flow is not created with a missing
        # hold message even if resolution order changes.
        for language in ("en_US", "es_US", "pt_BR"):
            require_hold_message(language, self._hold_messages.get(language))

        instance_arn = (
            f"arn:aws:connect:{self.region}:{self.account}:"
            f"instance/{self._cfg['INSTANCE_ID']}"
        )
        self._instance_arn = instance_arn

        # Resolve the queue hold-music prompt by NAME at deploy time (prompt
        # ids are instance-specific). The custom resource paginates
        # connect:ListPrompts and returns the matching prompt's ARN, which the
        # Loop prompts block references by PromptId so the music actually plays.
        music_prompt_name = require(
            "QUEUE_MUSIC_PROMPT_NAME", getattr(config, "QUEUE_MUSIC_PROMPT_NAME", None)
        )
        self._music_prompt = PromptByName(
            self,
            "QueueMusicPrompt",
            instance_id=self._cfg["INSTANCE_ID"],
            prompt_name=music_prompt_name,
        )

        replacements = {
            "__HOLD_MESSAGE_EN__": self._json_escape(self._hold_messages["en_US"]),
            "__HOLD_MESSAGE_ES__": self._json_escape(self._hold_messages["es_US"]),
            "__HOLD_MESSAGE_PT__": self._json_escape(self._hold_messages["pt_BR"]),
            "__TTS_VOICE_EN__": self._json_escape(self._cfg["TTS_VOICE_EN"]),
            "__TTS_VOICE_ES__": self._json_escape(self._cfg["TTS_VOICE_ES"]),
            "__TTS_VOICE_PT__": self._json_escape(self._cfg["TTS_VOICE_PT"]),
            "__TTS_ENGINE__": self._json_escape(self._cfg["TTS_ENGINE"]),
            # Resolved at deploy to the prompt ARN (a CDK token).
            "__QUEUE_MUSIC_PROMPT_ARN__": self._music_prompt.prompt_arn,
        }

        self._queue_flow = ContactFlow(
            self,
            "LocalizedQueueFlow",
            instance_arn=instance_arn,
            name=_QUEUE_FLOW_NAME,
            flow_path=_QUEUE_FLOW_PATH,
            flow_type="CUSTOMER_QUEUE",
            description=(
                "Customer-queue hold flow that branches internally on the "
                "contact's $.LanguageCode (java.util.Locale, e.g. es-US) and "
                "plays a localized hold message and TTS voice per language, "
                "defaulting to English."
            ),
            replacements=replacements,
        )
        # The Loop prompts block references the resolved music prompt ARN, so
        # ensure the lookup custom resource runs before the flow is created.
        self._queue_flow.flow.node.add_dependency(self._music_prompt.resource)

    def _create_init_flow_module(self) -> None:
        """Create the ``init-flow-es-v2`` contact flow module (ported from the
        live ``init-flow-es`` module in the instance).

        The module enables flow logging, sets the localized customer-queue flow
        as the ``CustomerQueue`` event hook (the "Set customer queue flow"
        block, ``UpdateContactEventHooks``), and configures per-channel
        recording/analytics. The ``-v2`` name avoids colliding with the
        original module that still exists in the instance. The queue-flow ARN
        marker is resolved at synth to the localized queue flow created above.
        """
        self._init_flow_module = ContactFlowModule(
            self,
            "InitFlowModule",
            instance_arn=self._instance_arn,
            name=config.INIT_FLOW_MODULE_NAME,
            flow_path=_INIT_FLOW_PATH,
            description=(
                "init-flow-es (v2): enables flow logging, sets the localized "
                "customer-queue flow as the CustomerQueue event hook, and "
                "configures per-channel recording/analytics."
            ),
            replacements={
                _QUEUE_FLOW_ARN_MARKER: self._queue_flow.flow_arn,
            },
        )
        # The Set-customer-queue-flow block references the localized queue flow,
        # so make sure that flow exists first.
        self._init_flow_module.node.add_dependency(self._queue_flow.flow)

    def _create_ai_prompts_and_agents(self) -> None:
        """Provision the localized Q in Connect prompts + utility agents (Deliverable 2).

        Phased rollout (Requirement 10): the localized utility AI prompts and
        agents are built for every enabled NON-English locale. ``en_US`` is
        always enabled for the queue experience (Deliverable 1), but it drives
        the localized queue flow, not a set of utility agents — so the AI-agent
        rollout iterates ``self._enabled_locales`` with ``en_US`` removed. With
        the current config that is ``es_US`` (Req 10.1); enabling ``pt_BR`` in
        ``config.LOCALES`` later (Req 10.2) extends the build with no code
        change, while a disabled/absent ``pt_BR`` yields no Portuguese
        resources (Req 10.3, resolved fail-closed in ``_resolve_config``).

        For each such locale the factory builds the FOUR distinct prompts once
        (the answer-generation prompt published a single time, Req 5.1/5.2),
        then the THREE utility agents:

          - Answer Recommendation — query reformulation + the SHARED
            answer-generation version + intent labeling (Requirements 6.1-6.4).
            (``suggestedMessages`` is not set: the native AWS::Wisdom::AIAgent
            CloudFormation resource does not expose that property.)
          - Manual Search — the SAME shared answer-generation version
            (Requirements 7.1-7.3).
          - Note Taking — the note-taking prompt version (Requirements 8.1-8.3).

        Results are stored on ``self`` keyed by locale + source/type so
        ``_create_outputs`` (task 10.4) can emit one ARN output per created
        prompt and agent::

            self._ai_prompts = {locale: {source: BuiltPrompt}}
            self._ai_agents  = {locale: {agent_type: LocalizedUtilityAIAgent}}

        Failure handling (Req 10.5): no exception is swallowed. A failure
        building any enabled locale propagates and fails the deploy, leaving no
        partial set — the factory itself raises (naming the missing reference)
        when a required prompt version is unavailable (Req 5.6/6.6/7.5/8.5).
        """
        assistant_id = self._cfg["ASSISTANT_ID"]

        # AI-agent rollout locales = enabled locales minus the English queue
        # locale. Order-preserving so synthesis is deterministic.
        ai_agent_locales = [
            locale for locale in self._enabled_locales if locale != "en_US"
        ]

        self._ai_prompts: dict[str, dict[str, ai_agents.BuiltPrompt]] = {}
        self._ai_agents: dict[str, dict[str, ai_agents.LocalizedUtilityAIAgent]] = {}

        for locale in ai_agent_locales:
            # 1) Build the four distinct prompts once (answer-generation once).
            prompts = ai_agents.build_localized_prompts(
                self,
                locale=locale,
                assistant_id=assistant_id,
            )
            self._ai_prompts[locale] = prompts

            shared_answer_generation_version = prompts[
                ai_agents.SOURCE_ANSWER_GENERATION
            ].version_id

            # 2) Build the three utility agents referencing the published
            #    versions; the shared answer-generation version is passed to
            #    BOTH the Answer Recommendation and Manual Search agents.
            answer_recommendation = ai_agents.build_answer_recommendation_agent(
                self,
                locale=locale,
                query_reformulation_prompt_version=prompts[
                    ai_agents.SOURCE_QUERY_REFORMULATION
                ].version_id,
                answer_generation_prompt_version=shared_answer_generation_version,
                intent_labeling_prompt_version=prompts[
                    ai_agents.SOURCE_INTENT_LABELING
                ].version_id,
                assistant_id=assistant_id,
            )
            manual_search = ai_agents.build_manual_search_agent(
                self,
                locale=locale,
                answer_generation_prompt_version=shared_answer_generation_version,
                assistant_id=assistant_id,
            )
            note_taking = ai_agents.build_note_taking_agent(
                self,
                locale=locale,
                note_taking_prompt_version=prompts[
                    ai_agents.SOURCE_NOTE_TAKING
                ].version_id,
                assistant_id=assistant_id,
            )

            self._ai_agents[locale] = {
                ai_agents.AGENT_TYPE_ANSWER_RECOMMENDATION: answer_recommendation,
                ai_agents.AGENT_TYPE_MANUAL_SEARCH: manual_search,
                ai_agents.AGENT_TYPE_NOTE_TAKING: note_taking,
            }

    def _create_outputs(self) -> None:
        """Emit one ``CfnOutput`` per CREATED resource (Requirement 11).

        Iterates the structures populated by the preceding phases so the set of
        ARN outputs corresponds exactly to the set of created resources — no
        output is emitted for a resource that was not created (Req 11.5). Each
        output value is the full ARN string (Req 11.4):

          - The single localized queue flow -> ``QueueFlowArn`` (Req 11.1).
          - Each created AI prompt -> ``AiPrompt<Source><Locale>Arn`` (Req 11.2),
            four per enabled AI-agent locale.
          - Each created AI agent -> ``AiAgent<Type><Locale>Arn`` (Req 11.3),
            three per enabled AI-agent locale.

        Logical ids are alphanumeric and unique: the source/type CamelCase token
        plus the CamelCase locale token (e.g. ``AiPromptAnswerGenerationEsUsArn``,
        ``AiAgentAnswerRecommendationEsUsArn``) distinguish every prompt and
        agent across locales.
        """
        # Queue flow (always created — Deliverable 1).
        CfnOutput(
            self,
            "QueueFlowArn",
            value=self._queue_flow.flow_arn,
            description="ARN of the localized customer-queue contact flow.",
        )

        # init-flow-es-v2 contact flow module (always created).
        CfnOutput(
            self,
            "InitFlowModuleArn",
            value=self._init_flow_module.module_arn,
            description="ARN of the init-flow-es-v2 contact flow module.",
        )

        # AI prompts — four per enabled AI-agent locale (Req 11.2).
        for locale, prompts in self._ai_prompts.items():
            locale_token = _locale_token(locale)
            for source, built in prompts.items():
                source_token = _PROMPT_SOURCE_TOKENS[source]
                CfnOutput(
                    self,
                    f"AiPrompt{source_token}{locale_token}Arn",
                    value=built.prompt.attr_ai_prompt_arn,
                    description=f"ARN of the {source} AI prompt ({locale}).",
                )

        # AI agents — three per enabled AI-agent locale (Req 11.3).
        for locale, agents in self._ai_agents.items():
            locale_token = _locale_token(locale)
            for agent_type, agent in agents.items():
                type_token = _AGENT_TYPE_TOKENS[agent_type]
                CfnOutput(
                    self,
                    f"AiAgent{type_token}{locale_token}Arn",
                    value=agent.ai_agent_arn,
                    description=f"ARN of the {agent_type} AI agent ({locale}).",
                )

    def _create_parameters(self) -> None:
        """Publish created resource ARNs to SSM Parameter Store.

        Other flows/stacks can then resolve the ARNs by stable name (e.g. a
        "Transfer to flow" block referencing the localized queue flow) without
        hard-coding them. Parameter names come from ``config.py``:

          - The localized queue flow ARN -> ``config.QUEUE_FLOW_PARAM_NAME``
            (``/flows/localized_queue_transfer``).
          - Each created AI agent ARN -> ``<config.AGENT_PARAM_PREFIX>/
            <agent_type_lowercase>_<locale>`` (e.g.
            ``/agents/answer_recommendation_es_US``), one per created agent so
            the parameters correspond exactly to the agents that were created.
        """
        # Queue flow ARN (always created — Deliverable 1).
        ssm.StringParameter(
            self,
            "QueueFlowParam",
            parameter_name=config.QUEUE_FLOW_PARAM_NAME,
            string_value=self._queue_flow.flow_arn,
            description="ARN of the localized customer-queue contact flow.",
        )

        # init-flow-es-v2 contact flow module ARN -> /flows/init/es.
        ssm.StringParameter(
            self,
            "InitFlowParam",
            parameter_name=config.INIT_FLOW_PARAM_NAME,
            string_value=self._init_flow_module.module_arn,
            description="ARN of the init-flow-es-v2 contact flow module.",
        )

        # One parameter per created AI agent, mirroring the queue-flow pattern.
        for locale, agents in self._ai_agents.items():
            locale_token = _locale_token(locale)
            for agent_type, agent in agents.items():
                type_token = _AGENT_TYPE_TOKENS[agent_type]
                ssm.StringParameter(
                    self,
                    f"AiAgent{type_token}{locale_token}Param",
                    parameter_name=(
                        f"{config.AGENT_PARAM_PREFIX}/{agent_type.lower()}_{locale}"
                    ),
                    string_value=agent.ai_agent_arn,
                    description=f"ARN of the {agent_type} AI agent ({locale}).",
                )
