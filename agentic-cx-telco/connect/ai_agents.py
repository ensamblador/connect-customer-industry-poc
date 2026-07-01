"""
connect/ai_agents.py — Q in Connect self-service AI agents (voice + chat) in CDK.

Native L1 all the way:

    CfnAIPrompt (orchestration prompt, YAML body) -> CfnAIPromptVersion
    CfnAIAgent  (orchestration agent + tools)     [no agent version is created]

Assigning a Connect security profile to each agent is a MANUAL post-deploy step
(Connect console / Admin website): there is no native CFN resource for
``connect:AssociateSecurityProfiles`` with EntityType=AI_AGENT, and rather than
carry a custom resource for it, the binding is left as documented manual ops
(see the project README).

Root-cause note — `maxLength` in a tool `inputSchema`:
An earlier revision saw orchestration fail on iteration 1 with "There was an
orchestration error for this nextMessageToken". The cause was a `maxLength`
field inside a tool's `inputSchema`: the `AWS::Wisdom::AIAgent` provider
serializes JSON-schema scalars as strings (`maxLength: "500"`), which is an
INVALID JSON Schema (maxLength must be an integer) and breaks orchestration
inference. The fix is simply to NOT put `maxLength` in tool input schemas. With
that removed, the native `CfnAIAgent` path works — no boto3 custom resource is
needed. (The empty `outputFilters: []` the provider also injects turned out to
be benign; the working reference agent runs fine alongside it.)

Tool surface (self-service): Retrieve (KB) + 9 AgentCore-gateway MCP tools +
Escalate/Complete RTC, plus ShowNewLineGuide (chat only).
"""

from __future__ import annotations

import json
from enum import Enum

from aws_cdk import aws_wisdom as wisdom
from constructs import Construct


# Self-service orchestration default model. Use the `global.` cross-region
# inference profile (matches the working console agent).
DEFAULT_MODEL_ID = "global.anthropic.claude-haiku-4-5-20251001-v1:0"

# The 9 AgentCore-gateway operations, with per-tool guidance.
TELCO_MCP_TOOLS = [
    {
        "name": "getAccountByPhone",
        "instruction": "Look up a customer account by phone number in E.164 format (e.g. +12065550101). The result includes the account id - reuse it for balance and line lookups.",
        "examples": ["Customer gives 206 555 0101 -> phoneNumber=\"+12065550101\"."],
    },
    {
        "name": "getAccountByEmail",
        "instruction": "Look up a customer account by email address. Use when the customer identifies by email. The result includes the account id.",
        "examples": ["Customer: \"maria.gonzalez@example.com\" -> email=\"maria.gonzalez@example.com\"."],
    },
    {
        "name": "getAccount",
        "instruction": "Get a customer's account profile by account id. Use after a phone/email lookup when the customer asks about their plan or account details.",
        "examples": ["Lookup returned accountId=\"acct-1001\" -> accountId=\"acct-1001\"."],
    },
    {
        "name": "getAccountBalance",
        "instruction": "Get the balance, currency, and due date for an account id. Use for balance or due-date questions, after you have the account id.",
        "examples": ["Customer asks their balance, accountId \"acct-1001\" -> accountId=\"acct-1001\"."],
    },
    {
        "name": "listPlans",
        "instruction": "List mobile plans, optionally filtered by a minimum data allowance in GB (minGb). Use for \"what plans do you have\" or \"which plan has the most data\".",
        "examples": ["Customer: \"plans with at least 50 GB\" -> minGb=50.", "Customer: \"what plans do you offer\" -> no filter."],
    },
    {
        "name": "getPlan",
        "instruction": "Get a single mobile plan's details by plan id. Use after listPlans when the customer wants the details or price of a specific plan.",
        "examples": ["Customer wants the Unlimited plan, id \"plan-unlimited\" -> planId=\"plan-unlimited\"."],
    },
    {
        "name": "newLine",
        "instruction": "Request a new mobile line for an existing customer. This is a state-changing action: the customer must confirm before it runs (user confirmation is enforced by the runtime). Provide the customerId (from an account lookup) and the planId for the new line; optionally a preferred 3-digit areaCode and notes. Tell the customer the returned line id and that the request is 'requested'.",
        "examples": ["Customer confirms a new line on plan-plus, customerId \"cust-5001\" -> customerId=\"cust-5001\", planId=\"plan-plus\", areaCode=\"206\"."],
        "requires_confirmation": True,
    },
    {
        "name": "listCustomerLines",
        "instruction": "List a customer's mobile lines and line requests by customerId. Use for \"my lines\" or \"the status of my new line request\", after you have the customerId from an account lookup.",
        "examples": ["Customer asks about their lines, customerId \"cust-5001\" -> customerId=\"cust-5001\"."],
    },
    {
        "name": "getLine",
        "instruction": "Get a line request's status and details by line id. Use when the customer gives a specific line id.",
        "examples": ["Customer: \"status of line-9001\" -> lineId=\"line-9001\"."],
    },
]

# NOTE (citations): the citation block below mirrors the SYSTEM default
# `AgentAssistanceOrchestrator` Retrieve tool instruction. Without it, the
# orchestration agent answers in plain text and the agent workspace renders NO
# "Sources" citations (and therefore no content-association affordance). Keep
# the `<message_part>` / `<sources><sourceId>` requirement when editing.
# Verified live: with this instruction the workspace shows Sources resolving to
# the cited KB content (e.g. esim-activacion). See the eSIM guide spec design
# doc for the full investigation (the step-by-step "start guide" button itself
# additionally depends on a Connect V2 platform gap, ref P365309129).
_RETRIEVE_INSTRUCTION = (
    "Use this to answer questions about plans, 4G/5G coverage, device "
    "compatibility, eSIM, store hours, roaming, and FAQs. Phrase the query as "
    "a complete, specific question, not keywords.\n\n"
    "When summarizing retrieve tool results, you MUST include source citations "
    "in the format shown in the good examples below. MUST ensure every "
    "message_part has sources. You can include preamble text like 'Here's what "
    "I found' but combine it with sourced content in the same message_part. "
    "MUST include source citations for ALL information from retrieve results. "
    "If retrieve returns no results or empty results, acknowledge that you "
    "don't have that specific information available; do not make assumptions or "
    "provide information from general knowledge."
)
_RETRIEVE_EXAMPLES = [
    (
        "Good example - message part with a source:\n"
        "<message>\n  <message_part>\n    <text>La activacion de la eSIM tarda "
        "unos minutos.</text>\n    <sources>\n      <sourceId>sampleSourceId_1"
        "</sourceId>\n    </sources>\n  </message_part>\n</message>"
    ),
    (
        "Bad example - information from retrieve results without a citation "
        "(avoid this):\n<message>\nLa activacion tarda unos minutos.\n</message>"
    ),
    "Example for no results:\n<message>\nNo tengo esa informacion disponible.\n</message>",
]

# Agent-assistance Retrieve tool — instruction + examples copied verbatim from
# the live agent-assist reference agent (connect-chat domain). The instruction
# is terse and the citation contract is taught entirely through the examples
# (multiple message parts, mixed cited/uncited, no-results). Agent-assist runs
# on Sonnet, which follows the example-driven format without the longer
# self-service preamble.
_ASSIST_RETRIEVE_INSTRUCTION = "Use this to answer questions about plans, 4G/5G coverage, device compatibility, eSIM, store hours, roaming, and FAQs. Phrase the query as a complete, specific question, not keywords."

_ASSIST_RETRIEVE_EXAMPLES = [
    "Good example - multiple message parts with sources.\n<message>\n  <message_part>\n    <text>This is the first part of the answer.</text>\n    <sources>\n      <sourceId>sampleSourceId_1</sourceId>\n      <sourceId>sampleSourceId_2</sourceId>\n    </sources>\n  </message_part>\n  <message_part>\n    <text>This is the second part with different sources.</text>\n    <sources>\n      <sourceId>sampleSourceId_3</sourceId>\n    </sources>\n  </message_part>\n</message>",
    "Good example - single message part with source\n <message>\n   <message_part>\n     <text>I found information about your warranty. It covers parts replacement for any manufacturing defects during the first year.</text>\n     <sources>\n       <sourceId>warranty_policy_2024</sourceId>\n     </sources>\n   </message_part>\n </message>",
    "Bad example - message parts without sources (avoid this):\n <message>\n   <message_part>\n     <text>Here's what I found about your warranty:</text>\n   </message_part>\n   <message_part>\n     <text>It covers parts replacement.</text>\n     <sources>\n       <sourceId>warranty_policy_2024</sourceId>\n     </sources>\n   </message_part>\n </message>",
    "Bad example - Text outside message parts after citations (avoid this):\n <message>\n   <message_part>\n     <text>Your warranty covers parts replacement for manufacturing defects.</text>\n     <sources>\n       <sourceId>warranty_policy_2024</sourceId>\n     </sources>\n   </message_part>\n   Let me know if you need anything else.\n </message>",
    "Bad example - Providing information from retrieve results without citations (avoid this):\n <message>\n We offer extended warranty coverage for eligible products beyond the manufacturer's warranty period.\n </message>",
    "Good example - some messages with citations and some without:\n<message>\n  <message_part>\n    <text>Based on our return policy, you can return most items within 30 days of purchase for a full refund. Items must be in original condition with receipt or proof of purchase.</text>\n    <sources>\n      <sourceId>return_policy_2024</sourceId>\n      <sourceId>customer_handbook_3_2</sourceId>\n    </sources>\n  </message_part>\n</message>\n\n<message>\nI'm still looking up the specific warranty coverage details for electronics. I'll have that information for you shortly.\n</message>",
    "Example for no results:\n<message>\nI don't have specific information about that topic available.\n</message>",
]

_ESCALATE_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "customerIntent": {"type": "string", "description": "Short phrase describing what the customer wants to accomplish."},
        "sentiment": {"type": "string", "description": "The customer's emotional state during the conversation.", "enum": ["positive", "neutral", "frustrated"]},
        "escalationSummary": {"type": "string", "description": "Brief summary for the human agent: what the customer asked, what was tried, and why escalation is needed."},
        "escalationReason": {"type": "string", "description": "Category of the escalation reason.", "enum": ["billing_question", "outage_or_service_issue", "account_inquiry_failed", "out_of_scope", "customer_request", "customer_frustration", "technical_issue", "other"]},
    },
    "required": ["escalationReason", "escalationSummary", "customerIntent", "sentiment"],
}
_ESCALATE_INSTRUCTION = (
    "Call this when: (1) the customer explicitly asks for a human; (2) the "
    "request is out of scope (payments, plan changes, removing/cancelling "
    "lines, billing disputes, legal/regulatory); (3) no available tool covers "
    "the request; (4) a tool keeps failing after you retried; or (5) you "
    "detect significant frustration. Emit a short <message> telling the customer "
    "you will transfer them first. Fill escalationReason with the most specific "
    "category; escalationSummary must capture what the customer asked, what you "
    "tried, and why a human is needed."
)

_COMPLETE_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "reason": {"type": "string", "description": "Why the conversation is being closed.", "enum": ["question_answered", "info_provided", "customer_satisfied", "no_further_needs", "other"]},
        "resolutionSummary": {"type": "string", "description": "Brief summary of what was resolved or provided."},
        "topicsDiscussed": {"type": "string", "description": "Topics covered in the conversation, comma-separated."},
    },
    "required": ["reason"],
}
_COMPLETE_INSTRUCTION = (
    "Call this ONLY after confirming the customer has no further questions or "
    "needs. Always ask 'Is there anything else I can help you with?' before "
    "using it. Emit a short, warm closing <message> first. Fill reason; when "
    "possible also fill resolutionSummary (brief) and topicsDiscussed."
)

_SHOW_NEWLINE_GUIDE_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "customerId": {"type": "string", "description": "The identified customer's id (from an account lookup). Required to launch the form."},
        "planId": {"type": "string", "description": "Pre-select this plan in the form if it was already discussed."},
        "areaCode": {"type": "string", "description": "Pre-fill a preferred 3-digit area code in the form if the customer mentioned one."},
    },
    "required": ["customerId"],
}
_SHOW_NEWLINE_GUIDE_INSTRUCTION = (
    "Chat only. Call this when a chat customer wants a new mobile line and you "
    "already have their customerId (from an account lookup). Emit a brief "
    "<message> first (e.g. tell them you'll open a short form), then invoke "
    "ShowNewLineGuide with the customerId; optionally pre-fill planId and a "
    "3-digit areaCode if they were already mentioned. Do NOT collect line "
    "details through the newLine tool conversationally on chat. If you do not "
    "have a customerId, identify the customer first; if you cannot identify "
    "them, Escalate instead."
)


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


def _retrieve_tool_dict(association_id, tag_filters, instruction=_RETRIEVE_INSTRUCTION, examples=_RETRIEVE_EXAMPLES) -> dict:
    """Build the Retrieve tool, filtering KB content by one or more tags.

    `tag_filters` is a list of (key, value) pairs. A single pair becomes a flat
    `{"equals": {...}}`; multiple pairs are AND-combined with `andAll` (the
    Bedrock/Q-in-Connect RetrievalFilter grammar) so e.g. industry=telco AND
    language=es restricts retrieval to the Spanish telco articles.

    `instruction`/`examples` default to the self-service citation contract;
    agent-assist passes its own (terser instruction, example-driven citations).
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


def _mcp_tool_dict(spec: dict, prefix: str, newline_confirmation: bool) -> dict:
    if spec["name"] == "newLine":
        confirmation = newline_confirmation
    else:
        confirmation = bool(spec.get("requires_confirmation"))
    return {
        "toolName": spec["name"],
        "toolType": "MODEL_CONTEXT_PROTOCOL",
        "toolId": f"{prefix}{spec['name']}",
        "instruction": _instr(spec["instruction"], spec.get("examples")),
        "userInteractionConfiguration": _uic(confirmation),
    }


def _escalate_tool_dict() -> dict:
    return {
        "toolName": "Escalate",
        "toolType": "RETURN_TO_CONTROL",
        "description": (
            "Ends the AI conversation and returns control to the Connect contact "
            "flow to transfer the contact to a human agent. Captures reason, "
            "intent, summary, and sentiment for the agent's screen."
        ),
        "instruction": _instr(_ESCALATE_INSTRUCTION, [
            "Customer: 'I want to pay my bill.' -> message then Escalate(escalationReason='out_of_scope', customerIntent='Make a payment', escalationSummary='Payments not available in self-service; transferring.', sentiment='neutral').",
        ]),
        "inputSchema": _ESCALATE_INPUT_SCHEMA,
        "userInteractionConfiguration": _uic(False),
    }


def _complete_tool_dict() -> dict:
    return {
        "toolName": "Complete",
        "toolType": "RETURN_TO_CONTROL",
        "description": (
            "Ends the AI conversation and returns control to the Connect contact "
            "flow when the customer has no further needs. Captures a short "
            "closing reason and summary for reporting."
        ),
        "instruction": _instr(_COMPLETE_INSTRUCTION, [
            "Good - question answered: emit a warm goodbye <message> then Complete(reason='question_answered', resolutionSummary='Confirmed 5G coverage in the customer area.', topicsDiscussed='coverage').",
        ]),
        "inputSchema": _COMPLETE_INPUT_SCHEMA,
        "userInteractionConfiguration": _uic(False),
    }


def _show_newline_guide_tool_dict() -> dict:
    return {
        "toolName": "ShowNewLineGuide",
        "toolType": "RETURN_TO_CONTROL",
        "description": (
            "Ends the AI turn and returns control to the flow to display a "
            "guided new-line request form in the chat window. Chat only."
        ),
        "instruction": _instr(_SHOW_NEWLINE_GUIDE_INSTRUCTION, [
            "Customer: 'quiero una linea nueva', already identified as customerId 'cust-5001' -> message then ShowNewLineGuide(customerId='cust-5001').",
            "Customer asked for the Plus plan on a new line, customerId 'cust-5001' -> ShowNewLineGuide(customerId='cust-5001', planId='plan-plus', areaCode='206').",
        ]),
        "inputSchema": _SHOW_NEWLINE_GUIDE_INPUT_SCHEMA,
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


def build_tools(
    surface: "AgentSurface",
    *,
    assistant_association_id: str,
    mcp_tool_prefix: str,
    content_tag_key: str = "industry",
    content_tag_value: str = "telco",
    content_language_key: str = "language",
    content_language: str | None = None,
) -> list[dict]:
    """Compose the clean tool-dict list for an agent surface.

      Voice : Retrieve + 9 MCP + Escalate + Complete                 (newLine confirm ON)
      Chat  : Retrieve + 9 MCP + Escalate + Complete + ShowNewLineGuide (newLine confirm OFF)
      Assist: Retrieve + 9 MCP only                                  (no handoff tools)

    The Retrieve tool filters KB content by `content_tag_key=content_tag_value`
    (industry=telco) and, when `content_language` is set, ALSO by
    `content_language_key=content_language` (e.g. language=es) — AND-combined so
    a Spanish agent never retrieves the pt/en copies of an article. Pass
    `content_language=None`/"" to retrieve across all languages.

    Tool dicts carry no `maxLength` in any inputSchema (provider stringifies it
    into an invalid schema) and set `overrideInputValues` only on Retrieve. The
    Retrieve tool's instruction/examples differ by surface: agent-assist gets
    its own (terser, example-driven) citation contract; voice/chat get the
    self-service one.
    """
    # newLine user-confirmation: ON for voice (verbal gate) and assist; OFF for
    # chat (the ShowNewLineGuide form is the explicit confirmation).
    newline_confirmation = surface is not AgentSurface.CHAT

    tag_filters = [(content_tag_key, content_tag_value)]
    if content_language:
        tag_filters.append((content_language_key, content_language))

    # Agent-assist uses its own Retrieve instruction/examples (copied from the
    # live agent-assist reference agent); voice/chat use the self-service ones.
    if surface is AgentSurface.ASSIST:
        retrieve = _retrieve_tool_dict(
            assistant_association_id, tag_filters,
            _ASSIST_RETRIEVE_INSTRUCTION, _ASSIST_RETRIEVE_EXAMPLES,
        )
    else:
        retrieve = _retrieve_tool_dict(assistant_association_id, tag_filters)

    tools = [retrieve]
    tools += [_mcp_tool_dict(t, mcp_tool_prefix, newline_confirmation) for t in TELCO_MCP_TOOLS]
    if surface in (AgentSurface.VOICE, AgentSurface.CHAT):
        tools.append(_escalate_tool_dict())
        tools.append(_complete_tool_dict())
    if surface is AgentSurface.CHAT:
        tools.append(_show_newline_guide_tool_dict())
    return tools


class OrchestrationAIAgent(Construct):
    """One Orchestration AI agent (native CfnAIAgent).

    Prompts are created separately (connect/ai_prompts.py); this construct
    creates only the native ``CfnAIAgent`` and its tool surface, binding the
    prompt version qualified id. NO agent version is created — the base agent
    ARN resolves to ``:$LATEST`` for the runtime. Tool input schemas must not
    carry `maxLength` (see module docstring).

    NOTE: assigning a Connect security profile to the agent is a MANUAL
    post-deploy step (done in the Connect console / Admin website). There is no
    native CloudFormation resource for ``connect:AssociateSecurityProfiles``
    with ``EntityType=AI_AGENT``; rather than carry a custom resource for it,
    the binding is left as documented manual ops (see the project README).
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
        locale: str,
        surface: "AgentSurface",
        assistant_association_id: str,
        mcp_tool_prefix: str,
        content_tag_key: str = "industry",
        content_tag_value: str = "telco",
        content_language_key: str = "language",
        content_language: str | None = None,
        description: str = "",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        tools = build_tools(
            surface,
            assistant_association_id=assistant_association_id,
            mcp_tool_prefix=mcp_tool_prefix,
            content_tag_key=content_tag_key,
            content_tag_value=content_tag_value,
            content_language_key=content_language_key,
            content_language=content_language,
        )
        agent_description = description or f"{agent_name} orchestration agent."

        # Native CfnAIAgent. _dict_to_cfn_tool sets override_input_values only
        # when populated and never sets output filters or maxLength.
        cfn_tools = [_dict_to_cfn_tool(t) for t in tools]
        self._cfn_agent = wisdom.CfnAIAgent(
            self,
            "Agent",
            assistant_id=assistant_id,
            name=agent_name,
            type="ORCHESTRATION",
            description=agent_description,
            configuration=wisdom.CfnAIAgent.AIAgentConfigurationProperty(
                orchestration_ai_agent_configuration=wisdom.CfnAIAgent.OrchestrationAIAgentConfigurationProperty(
                    orchestration_ai_prompt_id=prompt_version_id,
                    locale=locale,
                    connect_instance_arn=connect_instance_arn,
                    tool_configurations=cfn_tools,
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
