"""
connect/agent_tools.py — the AIRLINE AgentToolset (industry data for the agents).

All industry-specific agent data lives here: the 9 AgentCore-gateway MCP tools
(names + per-tool guidance), the self-service and agent-assist Retrieve
instructions/examples, the Escalate out-of-scope guidance + reason categories,
the Complete closing example, and the chat-only ShowReservationGuide form. The
reusable orchestration plumbing (the CfnAIAgent construct, tool composition,
Escalate/Complete skeletons) lives in ``cdk_constructs.connect.ai_agents``.

``AiAgentsStack`` imports ``TOOLSET`` from here and passes it to
``OrchestrationAIAgent``.
"""

from __future__ import annotations

from cdk_constructs.connect import AgentToolset, rtc_tool_dict

# The 9 AgentCore-gateway operations, with per-tool guidance (airline domain).
# ``createReservation`` is state-changing: confirmation ON for voice/assist, OFF
# on chat (the ShowReservationGuide form is the explicit confirmation there).
MCP_TOOLS = [
    {
        "name": "getAccountByPhone",
        "instruction": "Look up a customer account by phone number in E.164 format (e.g. +12065550101). The result includes the account id - reuse it for flight and reservation lookups.",
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
        "name": "getAccountFlights",
        "instruction": "Get the flights associated with a customer's account, plus their membership tier and miles balance. Use for \"my flights\", \"what flights do I have\", or miles balance questions.",
        "examples": ["Customer asks about their flights, accountId \"acct-1001\" -> accountId=\"acct-1001\"."],
    },
    {
        "name": "listFlights",
        "instruction": "List available flights, optionally filtered by origin and/or destination airport code (IATA 3-letter, e.g. BOG, MDE, LIM). Use for \"what flights are available\", \"flights from Bogotá to Lima\".",
        "examples": ["Customer: \"flights from Bogotá to Medellín\" -> origin=\"BOG\", destination=\"MDE\".", "Customer: \"what flights do you have\" -> no filter."],
    },
    {
        "name": "getFlight",
        "instruction": "Get a single flight's details by flight id. Use after listFlights when the customer wants details of a specific flight (schedule, price, seats).",
        "examples": ["Customer wants details of flight AL100, id \"flight-AL100\" -> flightId=\"flight-AL100\"."],
    },
    {
        "name": "createReservation",
        "instruction": "Create a new flight reservation for an existing customer. This is a state-changing action: the customer must confirm before it runs (user confirmation is enforced by the runtime). Provide the customerId (from an account lookup) and the flightId; optionally passengerName, email, date, time, and notes. Tell the customer the returned reservationId and that the status is 'pending'.",
        "examples": ["Customer confirms reservation for flight AL100, customerId \"cust-5001\" -> customerId=\"cust-5001\", flightId=\"flight-AL100\"."],
        "requires_confirmation": True,
        "confirmation_off_on_chat": True,
    },
    {
        "name": "listCustomerReservations",
        "instruction": "List a customer's reservations by customerId. Use for \"my reservations\" or \"the status of my booking\", after you have the customerId from an account lookup.",
        "examples": ["Customer asks about their reservations, customerId \"cust-5001\" -> customerId=\"cust-5001\"."],
    },
    {
        "name": "getReservation",
        "instruction": "Get a reservation's status and details by reservation id. Use when the customer gives a specific reservation id.",
        "examples": ["Customer: \"status of res-8001\" -> reservationId=\"res-8001\"."],
    },
]

# NOTE (citations): the citation block below mirrors the SYSTEM default
# `AgentAssistanceOrchestrator` Retrieve tool instruction. Without it, the
# orchestration agent answers in plain text and the agent workspace renders NO
# "Sources" citations. Keep the `<message_part>` / `<sources><sourceId>`
# requirement when editing.
RETRIEVE_INSTRUCTION = (
    "Use this to answer questions about reservations, the frequent-flyer "
    "program and miles, check-in, baggage, airports, lost or delayed baggage, "
    "and general FAQs. Phrase the query as a complete, specific question, not "
    "keywords.\n\n"
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
    "<message>\n  <message_part>\n    <text>El equipaje de mano permitido es "
    "una pieza por pasajero.</text>\n    <sources>\n      <sourceId>sampleSourceId_1"
    "</sourceId>\n    </sources>\n  </message_part>\n</message>"
)
_BAD_RETRIEVE_EXAMPLE = (
    "Bad example - information from retrieve results without a citation "
    "(avoid this):\n<message>\nEl equipaje de mano permitido es una pieza.\n</message>"
)
_NO_RESULTS_RETRIEVE_EXAMPLE = (
    "Example for no results:\n<message>\nNo tengo esa informacion disponible.\n</message>"
)
RETRIEVE_EXAMPLES = [
    _GOOD_RETRIEVE_EXAMPLE,
    _BAD_RETRIEVE_EXAMPLE,
    _NO_RESULTS_RETRIEVE_EXAMPLE,
]

# Agent-assist Retrieve instruction (terse; the citation contract is taught via
# the shared default examples on Sonnet).
ASSIST_RETRIEVE_INSTRUCTION = "Use this to answer questions about reservations, the frequent-flyer program and miles, check-in, baggage, airports, lost or delayed baggage, and general FAQs. Phrase the query as a complete, specific question, not keywords."

ESCALATE_INSTRUCTION = (
    "Call this when: (1) the customer explicitly asks for a human; (2) the "
    "request is out of scope (making payments, changing or cancelling "
    "reservations, closing accounts, billing disputes, legal/regulatory); (3) no available "
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
    "Good - question answered: emit a warm goodbye <message> then Complete(reason='question_answered', resolutionSummary='Confirmed the customer flights and reservation status.', topicsDiscussed='flights, reservations').",
]

# Chat-only guided reservation form (RETURN_TO_CONTROL).
_SHOW_RESERVATION_GUIDE_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "customerId": {"type": "string", "description": "The identified customer's id (from an account lookup). Required to launch the form."},
        "flightId": {"type": "string", "description": "Pre-select this flight in the form if it was already discussed."},
    },
    "required": ["customerId"],
}
_SHOW_RESERVATION_GUIDE_INSTRUCTION = (
    "Chat only. Call this when a chat customer wants to reserve a flight and "
    "you already have their customerId (from an account lookup). Emit a brief "
    "<message> first (e.g. tell them you'll open a short form), then invoke "
    "ShowReservationGuide with the customerId; optionally pre-fill flightId "
    "if it was already mentioned. Do NOT collect reservation details through the "
    "createReservation tool conversationally on chat. If you do not have a "
    "customerId, identify the customer first; if you cannot identify them, "
    "Escalate instead."
)

CHAT_TOOLS = (
    rtc_tool_dict(
        "ShowReservationGuide",
        description=(
            "Ends the AI turn and returns control to the flow to display a "
            "guided reservation form in the chat window. Chat only."
        ),
        instruction=_SHOW_RESERVATION_GUIDE_INSTRUCTION,
        input_schema=_SHOW_RESERVATION_GUIDE_INPUT_SCHEMA,
        examples=[
            "Customer: 'quiero reservar un vuelo', already identified as customerId 'cust-5001' -> message then ShowReservationGuide(customerId='cust-5001').",
            "Customer asked for flight AL100, customerId 'cust-5001' -> ShowReservationGuide(customerId='cust-5001', flightId='flight-AL100').",
        ],
    ),
)

TOOLSET = AgentToolset(
    content_tag_value="airline",
    mcp_tools=MCP_TOOLS,
    retrieve_instruction=RETRIEVE_INSTRUCTION,
    retrieve_examples=RETRIEVE_EXAMPLES,
    assist_retrieve_instruction=ASSIST_RETRIEVE_INSTRUCTION,
    escalate_instruction=ESCALATE_INSTRUCTION,
    escalate_reasons=ESCALATE_REASONS,
    complete_examples=tuple(COMPLETE_EXAMPLES),
    chat_tools=CHAT_TOOLS,
)
