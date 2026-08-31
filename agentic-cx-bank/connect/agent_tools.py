"""
connect/agent_tools.py — the BANKING AgentToolset (industry data for the agents).

All industry-specific agent data lives here: the 9 AgentCore-gateway MCP tools
(names + per-tool guidance), the self-service and agent-assist Retrieve
instructions/examples, the Escalate out-of-scope guidance + reason categories,
the Complete closing example, and the chat-only ShowCardRequestGuide form. The
reusable orchestration plumbing (the CfnAIAgent construct, tool composition,
Escalate/Complete skeletons) lives in ``cdk_constructs.connect.ai_agents``.

``AiAgentsStack`` imports ``TOOLSET`` from here and passes it to
``OrchestrationAIAgent``.
"""

from __future__ import annotations

from cdk_constructs.connect import AgentToolset, rtc_tool_dict

# The 9 AgentCore-gateway operations, with per-tool guidance (banking domain).
# ``requestCard`` is state-changing: confirmation ON for voice/assist, OFF on
# chat (the ShowCardRequestGuide form is the explicit confirmation there).
MCP_TOOLS = [
    {
        "name": "getAccountByPhone",
        "instruction": "Look up a customer account by phone number in E.164 format (e.g. +12065550101). The result includes the account id - reuse it for balance and card lookups.",
        "examples": ["Customer gives 206 555 0101 -> phoneNumber=\"+12065550101\"."],
    },
    {
        "name": "getAccountByEmail",
        "instruction": "Look up a customer account by email address. Use when the customer identifies by email. The result includes the account id.",
        "examples": ["Customer: \"maria.gonzalez@example.com\" -> email=\"maria.gonzalez@example.com\"."],
    },
    {
        "name": "getAccount",
        "instruction": "Get a customer's account profile by account id. Use after a phone/email lookup when the customer asks about their account details.",
        "examples": ["Lookup returned accountId=\"acct-1001\" -> accountId=\"acct-1001\"."],
    },
    {
        "name": "getAccountBalance",
        "instruction": "Get the balance, currency, and due date for an account id. Use for balance or due-date questions, after you have the account id.",
        "examples": ["Customer asks their balance, accountId \"acct-1001\" -> accountId=\"acct-1001\"."],
    },
    {
        "name": "listProducts",
        "instruction": "List banking products, optionally filtered by a maximum annual fee (maxAnnualFee). Use for \"what products do you have\" or \"which card has the lowest fee\".",
        "examples": ["Customer: \"cards with an annual fee under 50\" -> maxAnnualFee=50.", "Customer: \"what products do you offer\" -> no filter."],
    },
    {
        "name": "getProduct",
        "instruction": "Get a single banking product's details by product id. Use after listProducts when the customer wants the details or fees of a specific product.",
        "examples": ["Customer wants the Gold card, id \"prod-tarjeta-oro\" -> productId=\"prod-tarjeta-oro\"."],
    },
    {
        "name": "requestCard",
        "instruction": "Request a new card for an existing customer. This is a state-changing action: the customer must confirm before it runs (user confirmation is enforced by the runtime). Provide the customerId (from an account lookup) and the productId for the card; optionally notes. Tell the customer the returned card id and that the request is 'requested'.",
        "examples": ["Customer confirms a new gold card, customerId \"cust-5001\" -> customerId=\"cust-5001\", productId=\"prod-tarjeta-oro\"."],
        "requires_confirmation": True,
        "confirmation_off_on_chat": True,
    },
    {
        "name": "listCustomerCards",
        "instruction": "List a customer's cards and card requests by customerId. Use for \"my cards\" or \"the status of my new card request\", after you have the customerId from an account lookup.",
        "examples": ["Customer asks about their cards, customerId \"cust-5001\" -> customerId=\"cust-5001\"."],
    },
    {
        "name": "getCard",
        "instruction": "Get a card request's status and details by card id. Use when the customer gives a specific card id.",
        "examples": ["Customer: \"status of card-9001\" -> cardId=\"card-9001\"."],
    },
]

# NOTE (citations): mirrors the SYSTEM default `AgentAssistanceOrchestrator`
# Retrieve tool instruction. Keep the `<message_part>` / `<sources><sourceId>`
# requirement when editing.
RETRIEVE_INSTRUCTION = (
    "Use this to answer questions about accounts, cards, transfers, fees and "
    "commissions, activating a card, branch hours, and FAQs. Phrase the query "
    "as a complete, specific question, not keywords.\n\n"
    "When summarizing retrieve tool results, you MUST include source citations "
    "in the format shown in the good examples below. MUST ensure every "
    "message_part has sources. You can include preamble text like 'Here's what "
    "I found' but combine it with sourced content in the same message_part. "
    "MUST include source citations for ALL information from retrieve results. "
    "If retrieve returns no results or empty results, acknowledge that you "
    "don't have that specific information available; do not make assumptions or "
    "provide information from general knowledge."
)
_GOOD_RETRIEVE_EXAMPLE = (
    "Good example - message part with a source:\n"
    "<message>\n  <message_part>\n    <text>La activacion de la tarjeta tarda "
    "unos minutos.</text>\n    <sources>\n      <sourceId>sampleSourceId_1"
    "</sourceId>\n    </sources>\n  </message_part>\n</message>"
)
_BAD_RETRIEVE_EXAMPLE = (
    "Bad example - information from retrieve results without a citation "
    "(avoid this):\n<message>\nLa activacion tarda unos minutos.\n</message>"
)
_NO_RESULTS_RETRIEVE_EXAMPLE = (
    "Example for no results:\n<message>\nNo tengo esa informacion disponible.\n</message>"
)
RETRIEVE_EXAMPLES = [
    _GOOD_RETRIEVE_EXAMPLE,
    _BAD_RETRIEVE_EXAMPLE,
    _NO_RESULTS_RETRIEVE_EXAMPLE,
]

ASSIST_RETRIEVE_INSTRUCTION = "Use this to answer questions about accounts, cards, transfers, fees and commissions, activating a card, branch hours, and FAQs. Phrase the query as a complete, specific question, not keywords."

ESCALATE_INSTRUCTION = (
    "Call this when: (1) the customer explicitly asks for a human; (2) the "
    "request is out of scope (making payments or transfers, closing accounts, "
    "disputing charges or transactions, legal/regulatory); (3) no available "
    "tool covers the request; (4) a tool keeps failing after you retried; or "
    "(5) you detect significant frustration. Emit a short <message> telling the "
    "customer you will transfer them first. Fill escalationReason with the most "
    "specific category; escalationSummary must capture what the customer asked, "
    "what you tried, and why a human is needed."
)
ESCALATE_REASONS = (
    "billing_question",
    "transaction_or_service_issue",
    "account_inquiry_failed",
    "out_of_scope",
    "customer_request",
    "customer_frustration",
    "technical_issue",
    "other",
)

COMPLETE_EXAMPLES = [
    "Good - question answered: emit a warm goodbye <message> then Complete(reason='question_answered', resolutionSummary='Confirmed the customer account balance.', topicsDiscussed='balance').",
]

# Chat-only guided card-request form (RETURN_TO_CONTROL).
_SHOW_CARD_REQUEST_GUIDE_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "customerId": {"type": "string", "description": "The identified customer's id (from an account lookup). Required to launch the form."},
        "productId": {"type": "string", "description": "Pre-select this product in the form if it was already discussed."},
    },
    "required": ["customerId"],
}
_SHOW_CARD_REQUEST_GUIDE_INSTRUCTION = (
    "Chat only. Call this when a chat customer wants a new card and you "
    "already have their customerId (from an account lookup). Emit a brief "
    "<message> first (e.g. tell them you'll open a short form), then invoke "
    "ShowCardRequestGuide with the customerId; optionally pre-fill productId "
    "if it was already mentioned. Do NOT collect card details through the "
    "requestCard tool conversationally on chat. If you do not have a "
    "customerId, identify the customer first; if you cannot identify them, "
    "Escalate instead."
)

CHAT_TOOLS = (
    rtc_tool_dict(
        "ShowCardRequestGuide",
        description=(
            "Ends the AI turn and returns control to the flow to display a "
            "guided card request form in the chat window. Chat only."
        ),
        instruction=_SHOW_CARD_REQUEST_GUIDE_INSTRUCTION,
        input_schema=_SHOW_CARD_REQUEST_GUIDE_INPUT_SCHEMA,
        examples=[
            "Customer: 'quiero una tarjeta nueva', already identified as customerId 'cust-5001' -> message then ShowCardRequestGuide(customerId='cust-5001').",
            "Customer asked for the Gold card, customerId 'cust-5001' -> ShowCardRequestGuide(customerId='cust-5001', productId='prod-tarjeta-oro').",
        ],
    ),
)

TOOLSET = AgentToolset(
    content_tag_value="bank",
    mcp_tools=MCP_TOOLS,
    retrieve_instruction=RETRIEVE_INSTRUCTION,
    retrieve_examples=RETRIEVE_EXAMPLES,
    assist_retrieve_instruction=ASSIST_RETRIEVE_INSTRUCTION,
    escalate_instruction=ESCALATE_INSTRUCTION,
    escalate_reasons=ESCALATE_REASONS,
    complete_examples=tuple(COMPLETE_EXAMPLES),
    chat_tools=CHAT_TOOLS,
)
