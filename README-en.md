# Amazon Connect — Agentic Customer Experience PoC

> 🌐 **Languages:** [Español](./README.md) · **English** (this file)

> **Intelligent, omnichannel, multi-industry self-service** with Amazon Connect AI Agents, AI Agent Assist, and Bedrock AgentCore MCP.

This repository contains a complete proof of concept showing how to solve the most common contact center challenges using Amazon Connect's agentic capabilities. Each industry (telco, bank, airline) re-themes the same reference architecture with its own domain data and experiences, all sharing a single Connect instance.

---

## Challenges and Solutions

<table>
<tr>
<td width="50%" style="background-color:#fce4e4; vertical-align:top; padding:16px; color:#1a1a1a;">

### Simple interactions have to wait in the queue

Simple interactions require waiting for a human agent, with availability limited to 9-to-5 hours.

</td>
<td width="50%" style="background-color:#e4fce4; vertical-align:top; padding:16px; color:#1a1a1a;">

### Solution

**24/7 omnichannel agentic self-service** — Amazon Connect AI Agents resolve requests end to end over voice and chat, with no human involvement. The agent queries backend systems (MCP tools), searches the knowledge base, and escalates only when it genuinely cannot resolve.

</td>
</tr>
</table>

---

<table>
<tr>
<td width="50%" style="background-color:#fce4e4; vertical-align:top; padding:16px; color:#1a1a1a;">

### Static IVR with no flexibility

Static IVRs with no flexibility: rigid menu trees that frustrate the customer and never adapt to the conversation's context.

</td>
<td width="50%" style="background-color:#e4fce4; vertical-align:top; padding:16px; color:#1a1a1a;">

### Solution

**Conversational agentic service** — Instead of "Press 1 for...", the customer says what they need in natural language. The AI Agent understands the intent, keeps conversation context, reaches for tools, and resolves without rigid menu trees. The experience adapts dynamically to what the customer says: no menus, no frustration.

</td>
</tr>
</table>

---

<table>
<tr>
<td width="50%" style="background-color:#fce4e4; vertical-align:top; padding:16px; color:#1a1a1a;">

### Robotic, monotone voices

Robotic, monotone voices that build neither trust nor rapport with the customer.

</td>
<td width="50%" style="background-color:#e4fce4; vertical-align:top; padding:16px; color:#1a1a1a;">

### Solution

**Next-generation agentic voices** — Amazon Connect's new agentic voices are expressive and polyglot: they speak with natural intonation and rhythm, adapting to the conversation's context to build trust and rapport. A single voice handles Spanish, English and Portuguese, and the solution can be extended to **more than 38 languages and over 100 localization combinations** without rebuilding the flow.

</td>
</tr>
</table>

---

<table>
<tr>
<td width="50%" style="background-color:#fce4e4; vertical-align:top; padding:16px; color:#1a1a1a;">

### Self-service can't reach internal systems

Self-service cannot access internal systems: the bot answers generic questions but cannot check balances, make reservations, or execute real actions.

</td>
<td width="50%" style="background-color:#e4fce4; vertical-align:top; padding:16px; color:#1a1a1a;">

### Solution

**Domain tools and knowledge** — The AI Agent goes beyond answering generic questions: it queries business systems in real time through **purpose-built MCP tools for each industry** (look up accounts, list flights or products, create reservations) and leans on **domain knowledge bases** (multilingual) to resolve accurately. By combining action and knowledge, simple agentic interactions resolve autonomously, **taking load off human agents** and helping customers **resolve sooner**.

</td>
</tr>
</table>

---

<table>
<tr>
<td width="50%" style="background-color:#fce4e4; vertical-align:top; padding:16px; color:#1a1a1a;">

### Escalation to a human with no context

When self-service cannot resolve, the customer is transferred to a human agent with no context — and has to repeat everything from scratch.

</td>
<td width="50%" style="background-color:#e4fce4; vertical-align:top; padding:16px; color:#1a1a1a;">

### Solution

**Escalation with full context** — On escalation, the AI Agent records an `escalationSummary` with what was attempted and why it is escalating. The human agent gets a screen-pop with the customer's data, the conversation summary, and the AI Agent's tools at their disposal (AI Agent Assist).

</td>
</tr>
</table>

---

<table>
<tr>
<td width="50%" style="background-color:#fce4e4; vertical-align:top; padding:16px; color:#1a1a1a;">

### The agent loses time hunting for information

Human agents lose time searching for information across multiple systems while the customer waits on the line.

</td>
<td width="50%" style="background-color:#e4fce4; vertical-align:top; padding:16px; color:#1a1a1a;">

### Solution

**AI Agent Assist with real-time suggestions** — AI Agent Assist listens to the conversation and suggests answers from the knowledge base, runs MCP tools, and offers **step-by-step guides** when it detects a specific topic (e.g. "lost baggage" automatically surfaces the baggage reporting guide).

</td>
</tr>
</table>

---

<table>
<tr>
<td width="50%" style="background-color:#fce4e4; vertical-align:top; padding:16px; color:#1a1a1a;">

### Support in a single language

Support only works in one language, excluding a diverse customer base across Latin America.

</td>
<td width="50%" style="background-color:#e4fce4; vertical-align:top; padding:16px; color:#1a1a1a;">

### Solution

**Multilingual service with dynamic language switching** — Amazon Connect's polyglot voices switch language dynamically mid-conversation, with no flow changes. The AI Agent detects the customer's language from the transcript and replies in that language automatically.

</td>
</tr>
</table>

---

## Reference architecture

![](./connec-ai-agents.jpg)

### How it works

The diagram shows the journey of an interaction end to end:

1. **Omnichannel entry** — The customer reaches out via webchat, webcall or a phone call (PSTN). Every channel lands on a **single Amazon Connect instance**, with multilingual agentic voices (ES, EN, PT).
2. **Agentic self-service** — Connect routes the conversation to the **self-service AI Agent** (separate ones for Voice and Chat). The agent understands the intent in natural language and decides how to resolve it.
3. **Knowledge and action** — To resolve, the agent combines two reusable capabilities: **Retrieve** over a knowledge base (industry documents) and **MCP Tools** exposed by a Bedrock AgentCore gateway, which routes to each industry's business APIs.
4. **Escalation with context** — When the agent cannot resolve, it invokes the **Escalate Tool**: an escalation context is assembled (Guide) and the conversation moves to a human agent without the customer repeating anything.
5. **Helping the human agent** — With the human now on the line, **AI Agent Assist** rides along using the **same** knowledge base (Retrieve) and the **same** MCP Tools, suggesting answers and executing actions in real time.

**Conceptually:** a single Connect instance concentrates every channel; the AI Agent reads the customer's intent and orchestrates two shared resources — knowledge (KB) and tools (MCP) — in both self-service and human assistance. The same knowledge backend and the same tools serve both moments of the interaction.

**Benefit:** simple interactions resolve on their own 24/7, freeing human agents for the complex cases; and when escalation does happen, the human receives the full context and the same capabilities as the agent, handling it faster and with no friction for the customer. The architecture is multi-industry: the same base is re-themed (telco, banking, airline) by changing only the domain data and tools.

**Use cases by industry:**
- **Telco** → accounts, plans, mobile lines
- **Bank** → accounts, financial products, cards
- **Airline** → traveler accounts, available flights, reservations

---

## Repository Structure

```
connect-customer-industry-poc/
├── general-localization/       # CX-LANG-UTILS — localized queue, i18n prompts/agents, logging
├── agentic-cx-telco/           # CX-TELCO-* (6 stacks) — telecom demo
├── agentic-cx-bank/            # CX-BANCO-* (6 stacks) — banking demo
├── agentic-cx-airline/         # CX-AIRLINE-* (6 stacks) — airline demo
├── cdk_constructs/             # Shared CDK constructs (AgentCore, Connect, webhosting)
├── instructions.md             # Step-by-step deployment guide (Spanish)
├── instructions-en.md          # Step-by-step deployment guide (English)
├── README.md                   # Spanish version of this file
└── README-en.md                # This file
```

Each industry app contains:
```
agentic-cx-{industry}/
├── config.py                   # Centralized configuration (IDs, names, feature flags)
├── apis/                       # API Gateway REST API + OpenAPI spec
├── databases/                  # DynamoDB tables + seed data
├── lambdas/                    # Lambda handlers (per domain)
├── connect_ai_agents/          # Orchestration prompt YAMLs (voice/chat/assist)
├── connect/                    # Agent toolset (MCP tools + Retrieve + Escalate)
├── knowledge_bases/            # KB articles (es/pt/en) + tagging/association scripts
├── flows/                      # Contact flows (JSON, Flow Language)
├── views/                      # Customer-managed views (forms, step-by-step guides)
├── website/                    # Static site (Vite) with the chat widget
├── DEMO-WALKTHROUGH.md         # Demo script (Spanish)
├── DEMO-WALKTHROUGH-en.md      # Demo script (English)
└── agentic_cx_{industry}/      # CDK stacks (6 phases)
```

---

## Deployment

See **[instructions-en.md](./instructions-en.md)** for the complete step-by-step deployment guide, including:

- Prerequisites (CDK bootstrap, virtualenvs, credentials)
- Creating the Connect instance and the AI Agent Assist assistant (Q in Connect)
- Deploying `general-localization` (once)
- Deploying each industry (6 stacks per app)
- Post-deployment: KB tagging, guide association, security profiles, Lex bot, chat widget

Once deployed, each app carries a demo script with the exact questions to use: `agentic-cx-{industry}/DEMO-WALKTHROUGH-en.md`.

---

## Customization

### Editing the AI Agent prompts

The orchestration prompts are YAML files that define the agent's personality, rules and behavior:

```
connect_ai_agents/{industry}-selfservice-voice/prompts/   # Voice prompt
connect_ai_agents/{industry}-selfservice-chat/prompts/    # Chat prompt
connect_ai_agents/{industry}-agent-assist-es/prompts/     # Agent-assist prompt
```

Each prompt has editable sections:
- **`<identity>`** — The agent's personality and tone
- **`<core_behavior>`** — Numbered business rules (identification, escalation, confirmation)
- **`<customer_info>`** — Session variables injected by the flow
- **`<security>`** — Guardrails (don't reveal the system, don't give legal/medical advice)

After editing a prompt: `cdk deploy CX-{INDUSTRY}-AGENTS` and then **publish a new version** of the agent in the console.

### Changing the voice

The voice is configured on the **Lex V2 bot** → each locale → **Voice settings**:

1. In the Amazon Lex console → your bot → each locale → **Voice settings**
2. Pick a next-generation agentic (polyglot) voice or a language-specific voice
3. Rebuild the locale

The next-generation agentic voices are expressive and polyglot — one voice handles multiple languages without switching locale, and the solution can be extended to more than 38 languages and over 100 localization combinations.

### Editing the MCP tools

The tools the agent can invoke are defined in two places:

1. **`apis/openapi/openapi.yaml`** — The OpenAPI spec defines the operations (each `operationId` becomes an MCP tool)
2. **`connect/agent_tools.py`** — The per-tool instructions and examples that guide the agent on when and how to use each tool

To add a new tool: add the endpoint to the API + Lambda, add the `operationId` to the OpenAPI spec, register it in `config.AI_AGENT_MCP_OPERATIONS`, and add its guidance to `agent_tools.py`.

> Keep every string in `agent_tools.py` ASCII-only. Tool instructions and examples round-trip through CloudFormation into the Wisdom provider, which does not preserve non-ASCII bytes, so an accented word comes back mangled and `cdk diff` reports a permanent phantom change. Customer-facing copy with accents belongs in the prompt YAMLs.

### Editing the Knowledge Base

The articles live in `knowledge_bases/{industry}/entries/{language}/` as `.txt` files. To add content:

1. Create a `.txt` in the matching language folder (es/, pt/, en/)
2. Redeploy `CX-{INDUSTRY}-KB` (uploads the files to the S3 bucket)
3. Wait for the sync and run `python knowledge_bases/tag_kb_content.py --wait`

---

## Observability

### AI Agent logging (CloudWatch)

The `CX-LANG-UTILS` stack configures centralized delivery of the AI Agent Assist assistant's (Q in Connect) **EVENT_LOGS** to CloudWatch Logs. Controlled by `config.ENABLE_AGENT_LOGS`:

- **Log group:** `/aws/connect/wisdom/{assistant-id}/event-logs`
- **Contents:** Every agent invocation, tool calls, Retrieve results, escalations, and completions
- **Use it to:** Debug why an agent picked a given tool, verify citations are correct, audit escalations

### Demo data viewer

Each website exposes a `/datos` endpoint (Lambda + CloudFront) that renders the backend DynamoDB tables as HTML — handy for verifying the seed data is correct without opening the DynamoDB console.

### Contact Lens / Analytics

The inbound flow enables recording and analytics per channel. Contact Lens provides real-time transcription, sentiment analysis, and topic detection — wired into the escalation flow.

---

## Decommissioning the Project

To remove every deployed resource:

```bash
# 1. Destroy each industry's stacks (in reverse order)
cd agentic-cx-{industry}
source .venv/bin/activate
cdk destroy --all

# 2. Destroy general-localization
cd ../general-localization
source .venv/bin/activate
cdk destroy

# 3. Manual cleanup (if applicable):
#    - Delete the chat widget in the Connect console
#    - Delete the guide's content associations (associate_guide.py --delete, or by hand)
#    - Empty the S3 buckets before destroy if CDK cannot delete them
#    - Check no orphaned security profiles remain on the instance
```

> **Note:** The DynamoDB tables and the KB S3 buckets are configured with `RemovalPolicy.DESTROY` (demo). In production, switch them to `RETAIN`.

> **Destruction order:** Destroy the industries first (their flows reference the init module from `CX-LANG-UTILS`). If you destroy `CX-LANG-UTILS` first, the industry's `cdk destroy` can fail because it cannot find the SSM parameter `/flows/init/es`.

---

## License

This project is a proof of concept for demonstrations. See the LICENSE file (if present) for terms of use.
