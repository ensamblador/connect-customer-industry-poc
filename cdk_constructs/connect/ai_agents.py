"""
cdk_constructs/connect/ai_agents.py — Q in Connect self-service AI agents in CDK.

Industry-agnostic. This module carries ONLY the reusable orchestration
plumbing — the ``CfnAIAgent`` construct, the per-surface tool composition, the
generic Escalate/Complete RETURN_TO_CONTROL tools, and the dict→L1 converter.
Every domain-specific value (the MCP tool catalog, the Retrieve/Escalate
instructions, the chat "guide" tools, the content tag, the escalation-reason
enum) is supplied by each industry app through an ``AgentToolset`` built in the
app (see each app's ``connect/agent_tools.py``). Nothing here names an industry.

Native L1 all the way:

    CfnAIPrompt (orchestration prompt, YAML body) -> CfnAIPromptVersion  (ai_prompts.py)
    CfnAIAgent  (orchestration agent + tools)     [no agent version is created]

Assigning a Connect security profile to each agent is a MANUAL post-deploy step
(Connect console / Admin website): there is no native CFN resource for
``connect:AssociateSecurityProfiles`` with EntityType=AI_AGENT, and rather than
carry a custom resource for it, the binding is left as documented manual ops
(see each app's README).

Root-cause note — `maxLength` in a tool `inputSchema`:
An earlier revision saw orchestration fail on iteration 1 with "There was an
orchestration error for this nextMessageToken". The cause was a `maxLength`
field inside a tool's `inputSchema`: the `AWS::Wisdom::AIAgent` provider
serializes JSON-schema scalars as strings (`maxLength: "500"`), which is an
INVALID JSON Schema (maxLength must be an integer) and breaks orchestration
inference. The fix is simply to NOT put `maxLength` in tool input schemas.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum

from aws_cdk import aws_wisdom as wisdom
from constructs import Construct


# Self-service orchestration default model. Use the `global.` cross-region
# inference profile (matches the working console agent).
DEFAULT_MODEL_ID = "global.anthropic.claude-haiku-4-5-20251001-v1:0"

# --------------------------------------------------------------------------- #
# Neutral defaults. These carry NO industry token, so an app only overrides the
# pieces that actually differ for its domain. The Escalate/Complete descriptions
# and the Complete instruction are generic RETURN_TO_CONTROL contracts; the
# agent-assist Retrieve examples are the domain-free reference set.
# --------------------------------------------------------------------------- #
DEFAULT_ESCALATE_DESCRIPTION = (
    "Ends the AI conversation and returns control to the Connect contact "
    "flow to transfer the contact to a human agent. Captures reason, "
    "intent, summary, and sentiment for the agent's screen."
)
DEFAULT_ESCALATE_EXAMPLES = [
    "Customer: 'I want to pay my bill.' -> message then Escalate(escalationReason='out_of_scope', customerIntent='Make a payment', escalationSummary='Payments not available in self-service; transferring.', sentiment='neutral').",
]
# Escalation-reason categories. Most are cross-industry; an app overrides the
# whole tuple when it needs a domain-specific category (e.g. one domain uses
# ``transaction_or_service_issue`` where another uses ``outage_or_service_issue``).
DEFAULT_ESCALATE_REASONS = (
    "billing_question",
    "service_issue",
    "account_inquiry_failed",
    "out_of_scope",
    "customer_request",
    "customer_frustration",
    "technical_issue",
    "other",
)

DEFAULT_COMPLETE_DESCRIPTION = (
    "Ends the AI conversation and returns control to the Connect contact "
    "flow when the customer has no further needs. Captures a short "
    "closing reason and summary for reporting."
)
DEFAULT_COMPLETE_INSTRUCTION = (
    "Call this ONLY after confirming the customer has no further questions or "
    "needs. Always ask 'Is there anything else I can help you with?' before "
    "using it. Emit a short, warm closing <message> first. Fill reason; when "
    "possible also fill resolutionSummary (brief) and topicsDiscussed."
)
DEFAULT_COMPLETE_EXAMPLES = [
    "Good - question answered: emit a warm goodbye <message> then Complete(reason='question_answered', resolutionSummary='Answered the customer question.', topicsDiscussed='general').",
]

# Agent-assistance Retrieve examples — copied verbatim from the live agent-assist
# reference agent. Domain-free (warranty / return / generic), so they are a
# shared default; the INSTRUCTION that precedes them is domain-specific and comes
# from the toolset.
DEFAULT_ASSIST_RETRIEVE_EXAMPLES = [
    "Good example - multiple message parts with sources.\n<message>\n  <message_part>\n    <text>This is the first part of the answer.</text>\n    <sources>\n      <sourceId>sampleSourceId_1</sourceId>\n      <sourceId>sampleSourceId_2</sourceId>\n    </sources>\n  </message_part>\n  <message_part>\n    <text>This is the second part with different sources.</text>\n    <sources>\n      <sourceId>sampleSourceId_3</sourceId>\n    </sources>\n  </message_part>\n</message>",
    "Good example - single message part with source\n <message>\n   <message_part>\n     <text>I found information about your warranty. It covers parts replacement for any manufacturing defects during the first year.</text>\n     <sources>\n       <sourceId>warranty_policy_2024</sourceId>\n     </sources>\n   </message_part>\n </message>",
    "Bad example - message parts without sources (avoid this):\n <message>\n   <message_part>\n     <text>Here's what I found about your warranty:</text>\n   </message_part>\n   <message_part>\n     <text>It covers parts replacement.</text>\n     <sources>\n       <sourceId>warranty_policy_2024</sourceId>\n     </sources>\n   </message_part>\n </message>",
    "Bad example - Text outside message parts after citations (avoid this):\n <message>\n   <message_part>\n     <text>Your warranty covers parts replacement for manufacturing defects.</text>\n     <sources>\n       <sourceId>warranty_policy_2024</sourceId>\n     </sources>\n   </message_part>\n   Let me know if you need anything else.\n </message>",
    "Bad example - Providing information from retrieve results without citations (avoid this):\n <message>\n We offer extended warranty coverage for eligible products beyond the manufacturer's warranty period.\n </message>",
    "Good example - some messages with citations and some without:\n<message>\n  <message_part>\n    <text>Based on our return policy, you can return most items within 30 days of purchase for a full refund. Items must be in original condition with receipt or proof of purchase.</text>\n    <sources>\n      <sourceId>return_policy_2024</sourceId>\n      <sourceId>customer_handbook_3_2</sourceId>\n    </sources>\n  </message_part>\n</message>\n\n<message>\nI'm still looking up the specific warranty coverage details for electronics. I'll have that information for you shortly.\n</message>",
    "Example for no results:\n<message>\nI don't have specific information about that topic available.\n</message>",
]

_COMPLETE_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "reason": {"type": "string", "description": "Why the conversation is being closed.", "enum": ["question_answered", "info_provided", "customer_satisfied", "no_further_needs", "other"]},
        "resolutionSummary": {"type": "string", "description": "Brief summary of what was resolved or provided."},
        "topicsDiscussed": {"type": "string", "description": "Topics covered in the conversation, comma-separated."},
    },
    "required": ["reason"],
}


def _escalate_input_schema(reasons) -> dict:
    """Build the Escalate inputSchema with the given escalation-reason enum."""
    return {
        "type": "object",
        "properties": {
            "customerIntent": {"type": "string", "description": "Short phrase describing what the customer wants to accomplish."},
            "sentiment": {"type": "string", "description": "The customer's emotional state during the conversation.", "enum": ["positive", "neutral", "frustrated"]},
            "escalationSummary": {"type": "string", "description": "Brief summary for the human agent: what the customer asked, what was tried, and why escalation is needed."},
            "escalationReason": {"type": "string", "description": "Category of the escalation reason.", "enum": list(reasons)},
        },
        "required": ["escalationReason", "escalationSummary", "customerIntent", "sentiment"],
    }


# --------------------------------------------------------------------------- #
# Plain-dict tool builders. Kept as plain dicts (then converted to L1 props by
# _dict_to_cfn_tool) so the same shapes are easy to read/validate. Only set
# overrideInputValues when populated; never put `maxLength` in an inputSchema
# (the provider stringifies it -> invalid JSON Schema -> orchestration error).
# --------------------------------------------------------------------------- #
def _instr(text: str, examples=None) -> dict:
    d = {"instruction": text}
    if examples:
        d["examples"] = list(examples)
    return d


def _uic(required: bool) -> dict:
    return {"isUserConfirmationRequired": bool(required)}


def rtc_tool_dict(
    name: str,
    *,
    description: str,
    instruction: str,
    input_schema: dict,
    examples=None,
    user_confirmation_required: bool = False,
) -> dict:
    """Build a RETURN_TO_CONTROL tool dict (e.g. an industry chat "guide" form).

    Apps use this to declare their chat-only guide tools (a card-request form, a
    new-line form, an eSIM guide, …) in an ``AgentToolset.chat_tools`` list,
    without depending on the internal dict shape.
    """
    return {
        "toolName": name,
        "toolType": "RETURN_TO_CONTROL",
        "description": description,
        "instruction": _instr(instruction, examples),
        "inputSchema": input_schema,
        "userInteractionConfiguration": _uic(user_confirmation_required),
    }


def _retrieve_tool_dict(association_id, tag_filters, instruction, examples) -> dict:
    """Build the Retrieve tool, filtering KB content by one or more tags.

    `tag_filters` is a list of (key, value) pairs. A single pair becomes a flat
    `{"equals": {...}}`; multiple pairs are AND-combined with `andAll` (the
    Bedrock/Q-in-Connect RetrievalFilter grammar) so e.g. industry=<x> AND
    language=es restricts retrieval to the Spanish articles for that industry.
    """
    equals = [{"equals": {"key": k, "value": v}} for k, v in tag_filters]
    retrieval_filter = equals[0] if len(equals) == 1 else {"andAll": equals}
    return {
        "toolName": "Retrieve",
        "toolType": "MODEL_CONTEXT_PROTOCOL",
        "toolId": "aws_service__qconnect_Retrieve",
        "instruction": _instr(instruction, examples),
        "userInteractionConfiguration": _uic(False),
        "overrideInputValues": [
            {"jsonPath": "$.retrievalConfiguration.knowledgeSource.assistantAssociationIds",
             "value": {"constant": {"type": "JSON_STRING", "value": json.dumps([association_id])}}},
            {"jsonPath": "$.retrievalConfiguration.filter",
             "value": {"constant": {"type": "JSON_STRING", "value": json.dumps(retrieval_filter)}}},
            {"jsonPath": "$.assistantId",
             "value": {"constant": {"type": "STRING", "value": "{{$.assistantId}}"}}},
        ],
    }


def _mcp_tool_dict(spec: dict, prefix: str, surface: "AgentSurface") -> dict:
    """Build an MCP gateway tool dict from a catalog `spec`.

    A tool marked ``requires_confirmation`` gates on user confirmation; if it is
    also marked ``confirmation_off_on_chat`` the confirmation is dropped on the
    CHAT surface (where an explicit guide form is the confirmation instead).
    """
    confirmation = bool(spec.get("requires_confirmation"))
    if surface is AgentSurface.CHAT and spec.get("confirmation_off_on_chat"):
        confirmation = False
    return {
        "toolName": spec["name"],
        "toolType": "MODEL_CONTEXT_PROTOCOL",
        "toolId": f"{prefix}{spec['name']}",
        "instruction": _instr(spec["instruction"], spec.get("examples")),
        "userInteractionConfiguration": _uic(confirmation),
    }


def _escalate_tool_dict(toolset: "AgentToolset") -> dict:
    return {
        "toolName": "Escalate",
        "toolType": "RETURN_TO_CONTROL",
        "description": toolset.escalate_description,
        "instruction": _instr(toolset.escalate_instruction, list(toolset.escalate_examples)),
        "inputSchema": _escalate_input_schema(toolset.escalate_reasons),
        "userInteractionConfiguration": _uic(False),
    }


def _complete_tool_dict(toolset: "AgentToolset") -> dict:
    return {
        "toolName": "Complete",
        "toolType": "RETURN_TO_CONTROL",
        "description": toolset.complete_description,
        "instruction": _instr(toolset.complete_instruction, list(toolset.complete_examples)),
        "inputSchema": _COMPLETE_INPUT_SCHEMA,
        "userInteractionConfiguration": _uic(False),
    }


def _dict_to_cfn_tool(d: dict) -> "wisdom.CfnAIAgent.ToolConfigurationProperty":
    """Convert a tool dict to a CfnAIAgent.ToolConfigurationProperty."""
    instr = d["instruction"]
    kwargs = dict(
        tool_name=d["toolName"],
        tool_type=d["toolType"],
        instruction=wisdom.CfnAIAgent.ToolInstructionProperty(
            instruction=instr["instruction"],
            examples=instr.get("examples"),
        ),
        user_interaction_configuration=wisdom.CfnAIAgent.UserInteractionConfigurationProperty(
            is_user_confirmation_required=d["userInteractionConfiguration"]["isUserConfirmationRequired"],
        ),
    )
    if d.get("toolId"):
        kwargs["tool_id"] = d["toolId"]
    if d.get("description"):
        kwargs["description"] = d["description"]
    if d.get("inputSchema"):
        kwargs["input_schema"] = d["inputSchema"]
    if d.get("overrideInputValues"):
        kwargs["override_input_values"] = [
            wisdom.CfnAIAgent.ToolOverrideInputValueProperty(
                json_path=o["jsonPath"],
                value=wisdom.CfnAIAgent.ToolOverrideInputValueConfigurationProperty(
                    constant=wisdom.CfnAIAgent.ToolOverrideConstantInputValueProperty(
                        type=o["value"]["constant"]["type"],
                        value=o["value"]["constant"]["value"],
                    )
                ),
            )
            for o in d["overrideInputValues"]
        ]
    return wisdom.CfnAIAgent.ToolConfigurationProperty(**kwargs)


class AgentSurface(Enum):
    """Drives the per-agent tool surface."""

    VOICE = "voice"
    CHAT = "chat"
    ASSIST = "assist"


@dataclass(frozen=True)
class AgentToolset:
    """Industry-supplied data that shapes an agent's tool surface.

    Required (domain-specific): the MCP tool catalog, the content tag value, the
    self-service + agent-assist Retrieve instructions/examples, the Escalate
    instruction. Everything else has a neutral default an app can override.

    `mcp_tools` entries are dicts: ``{"name", "instruction", "examples"?,
    "requires_confirmation"?, "confirmation_off_on_chat"?}``. `chat_tools` are
    RETURN_TO_CONTROL tool dicts (build them with ``rtc_tool_dict``) appended on
    the CHAT surface only.
    """

    content_tag_value: str
    mcp_tools: list
    retrieve_instruction: str
    retrieve_examples: list
    assist_retrieve_instruction: str
    escalate_instruction: str

    content_tag_key: str = "industry"
    chat_tools: tuple = ()
    assist_retrieve_examples: tuple = tuple(DEFAULT_ASSIST_RETRIEVE_EXAMPLES)
    escalate_examples: tuple = tuple(DEFAULT_ESCALATE_EXAMPLES)
    escalate_reasons: tuple = DEFAULT_ESCALATE_REASONS
    escalate_description: str = DEFAULT_ESCALATE_DESCRIPTION
    complete_instruction: str = DEFAULT_COMPLETE_INSTRUCTION
    complete_examples: tuple = tuple(DEFAULT_COMPLETE_EXAMPLES)
    complete_description: str = DEFAULT_COMPLETE_DESCRIPTION


def build_tools(
    surface: "AgentSurface",
    toolset: "AgentToolset",
    *,
    assistant_association_id: str,
    mcp_tool_prefix: str,
    content_language_key: str = "language",
    content_language: str | None = None,
) -> list:
    """Compose the tool-dict list for an agent surface from an ``AgentToolset``.

      Voice : Retrieve + N MCP + Escalate + Complete
      Chat  : Retrieve + N MCP + Escalate + Complete + chat_tools (guide forms)
      Assist: Retrieve + N MCP only                              (no handoff tools)

    The Retrieve tool filters KB content by ``content_tag_key=content_tag_value``
    and, when `content_language` is set, ALSO by
    ``content_language_key=content_language`` (AND-combined) so a Spanish agent
    never retrieves the pt/en copies. Pass ``content_language=None``/"" to
    retrieve across all languages. Agent-assist uses the toolset's assist
    Retrieve instruction/examples; voice/chat use the self-service ones.
    """
    tag_filters = [(toolset.content_tag_key, toolset.content_tag_value)]
    if content_language:
        tag_filters.append((content_language_key, content_language))

    if surface is AgentSurface.ASSIST:
        retrieve = _retrieve_tool_dict(
            assistant_association_id, tag_filters,
            toolset.assist_retrieve_instruction, list(toolset.assist_retrieve_examples),
        )
    else:
        retrieve = _retrieve_tool_dict(
            assistant_association_id, tag_filters,
            toolset.retrieve_instruction, list(toolset.retrieve_examples),
        )

    tools = [retrieve]
    tools += [_mcp_tool_dict(t, mcp_tool_prefix, surface) for t in toolset.mcp_tools]
    if surface in (AgentSurface.VOICE, AgentSurface.CHAT):
        tools.append(_escalate_tool_dict(toolset))
        tools.append(_complete_tool_dict(toolset))
    if surface is AgentSurface.CHAT:
        tools += list(toolset.chat_tools)
    return tools


class OrchestrationAIAgent(Construct):
    """One Orchestration AI agent (native CfnAIAgent).

    Prompts are created separately (ai_prompts.py); this construct creates only
    the native ``CfnAIAgent`` and its tool surface (built from ``toolset``),
    binding the prompt version qualified id. NO agent version is created — the
    base agent ARN resolves to ``:$LATEST`` for the runtime. Tool input schemas
    must not carry `maxLength` (see module docstring).

    NOTE: assigning a Connect security profile to the agent is a MANUAL
    post-deploy step (Connect console / Admin website). There is no native
    CloudFormation resource for ``connect:AssociateSecurityProfiles`` with
    ``EntityType=AI_AGENT``; the binding is left as documented manual ops.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        assistant_id: str,
        connect_instance_arn: str,
        agent_name: str,
        prompt_version_id: str,
        locale: str = "",
        surface: "AgentSurface",
        toolset: "AgentToolset",
        assistant_association_id: str,
        mcp_tool_prefix: str,
        content_language_key: str = "language",
        content_language: str | None = None,
        description: str = "",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        tools = build_tools(
            surface,
            toolset,
            assistant_association_id=assistant_association_id,
            mcp_tool_prefix=mcp_tool_prefix,
            content_language_key=content_language_key,
            content_language=content_language,
        )
        agent_description = description or f"{agent_name} orchestration agent."

        # Native CfnAIAgent. _dict_to_cfn_tool sets override_input_values only
        # when populated and never sets output filters or maxLength.
        cfn_tools = [_dict_to_cfn_tool(t) for t in tools]

        # Build orchestration config; omit locale when empty (multilingual mode).
        orchestration_props: dict = dict(
            orchestration_ai_prompt_id=prompt_version_id,
            connect_instance_arn=connect_instance_arn,
            tool_configurations=cfn_tools,
        )
        if locale:
            orchestration_props["locale"] = locale

        self._cfn_agent = wisdom.CfnAIAgent(
            self,
            "Agent",
            assistant_id=assistant_id,
            name=agent_name,
            type="ORCHESTRATION",
            description=agent_description,
            configuration=wisdom.CfnAIAgent.AIAgentConfigurationProperty(
                orchestration_ai_agent_configuration=wisdom.CfnAIAgent.OrchestrationAIAgentConfigurationProperty(
                    **orchestration_props,
                )
            ),
        )

    # ------------------------------------------------------------------ #
    @property
    def cfn_agent(self) -> "wisdom.CfnAIAgent":
        """The native CfnAIAgent — for escape-hatch overrides."""
        return self._cfn_agent

    @property
    def ai_agent_id(self) -> str:
        return self._cfn_agent.attr_ai_agent_id

    @property
    def ai_agent_arn(self) -> str:
        return self._cfn_agent.attr_ai_agent_arn
