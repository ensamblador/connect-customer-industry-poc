"""
connect/agent_tools.py — the TELCO AgentToolset (industry data for the agents).

All industry-specific agent data lives here: the 9 AgentCore-gateway MCP tools
(names + per-tool guidance), the self-service and agent-assist Retrieve
instructions/examples, the Escalate out-of-scope guidance + reason categories,
the Complete closing example, and the chat-only ShowNewLineGuide form. The
reusable orchestration plumbing (the CfnAIAgent construct, tool composition,
Escalate/Complete skeletons) lives in ``cdk_constructs.connect.ai_agents``.

``AiAgentsStack`` imports ``TOOLSET`` from here and passes it to
``OrchestrationAIAgent``.
"""

from __future__ import annotations

from cdk_constructs.connect import AgentToolset, rtc_tool_dict

# The 9 AgentCore-gateway operations, with per-tool guidance (telco domain).
# ``newLine`` is state-changing: confirmation ON for voice/assist, OFF on chat
# (the ShowNewLineGuide form is the explicit confirmation there).
MCP_TOOLS = [
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
        "confirmation_off_on_chat": True,
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

# NOTE (citations): mirrors the SYSTEM default `AgentAssistanceOrchestrator`
# Retrieve tool instruction. Keep the `<message_part>` / `<sources><sourceId>`
# requirement when editing.
RETRIEVE_INSTRUCTION = (
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
RETRIEVE_EXAMPLES = [
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

ASSIST_RETRIEVE_INSTRUCTION = "Use this to answer questions about plans, 4G/5G coverage, device compatibility, eSIM, store hours, roaming, and FAQs. Phrase the query as a complete, specific question, not keywords."

ESCALATE_INSTRUCTION = (
    "Call this when: (1) the customer explicitly asks for a human; (2) the "
    "request is out of scope (payments, plan changes, removing/cancelling "
    "lines, billing disputes, legal/regulatory); (3) no available tool covers "
    "the request; (4) a tool keeps failing after you retried; or (5) you "
    "detect significant frustration. Emit a short <message> telling the customer "
    "you will transfer them first. Fill escalationReason with the most specific "
    "category; escalationSummary must capture what the customer asked, what you "
    "tried, and why a human is needed."
)
ESCALATE_REASONS = (
    "billing_question",
    "outage_or_service_issue",
    "account_inquiry_failed",
    "out_of_scope",
    "customer_request",
    "customer_frustration",
    "technical_issue",
    "other",
)

COMPLETE_EXAMPLES = [
    "Good - question answered: emit a warm goodbye <message> then Complete(reason='question_answered', resolutionSummary='Confirmed 5G coverage in the customer area.', topicsDiscussed='coverage').",
]

# Chat-only guided new-line request form (RETURN_TO_CONTROL).
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

CHAT_TOOLS = (
    rtc_tool_dict(
        "ShowNewLineGuide",
        description=(
            "Ends the AI turn and returns control to the flow to display a "
            "guided new-line request form in the chat window. Chat only."
        ),
        instruction=_SHOW_NEWLINE_GUIDE_INSTRUCTION,
        input_schema=_SHOW_NEWLINE_GUIDE_INPUT_SCHEMA,
        examples=[
            "Customer: 'quiero una linea nueva', already identified as customerId 'cust-5001' -> message then ShowNewLineGuide(customerId='cust-5001').",
            "Customer asked for the Plus plan on a new line, customerId 'cust-5001' -> ShowNewLineGuide(customerId='cust-5001', planId='plan-plus', areaCode='206').",
        ],
    ),
)

TOOLSET = AgentToolset(
    content_tag_value="telco",
    mcp_tools=MCP_TOOLS,
    retrieve_instruction=RETRIEVE_INSTRUCTION,
    retrieve_examples=RETRIEVE_EXAMPLES,
    assist_retrieve_instruction=ASSIST_RETRIEVE_INSTRUCTION,
    escalate_instruction=ESCALATE_INSTRUCTION,
    escalate_reasons=ESCALATE_REASONS,
    complete_examples=tuple(COMPLETE_EXAMPLES),
    chat_tools=CHAT_TOOLS,
)
