# agentic-cx-telco

A phased AWS CDK (Python) sample that stands up a **telco self-service backend**
and exposes it to **Amazon Connect AI agents** as an MCP server through a Bedrock
AgentCore gateway, plus a **Q in Connect knowledge base** for retrieval and the
**Connect supporting resources** (security profiles, views, guides) the agents
use. The app is split into small, decoupled stacks that deploy independently and
pass values to each other only through **SSM Parameter Store** — no
CloudFormation exports, no nested stacks.

| Deploy command | Stack | What it deploys |
|---|---|---|
| `cdk deploy CX-TELCO-MCP` | `McpStack` (Phase 1) | DynamoDB tables + sample data, the Lambda backend, the Telco REST API, the AgentCore MCP gateway, and the Amazon Connect MCP/Lambda integrations |
| `cdk deploy CX-TELCO-KB` | `KnowledgeBaseStack` (Phase 2) | The S3-backed EXTERNAL Q in Connect knowledge base (es/pt/en content) and its assistant association |
| `cdk deploy CX-TELCO-CONNECT-SUPPORT` | `ConnectSupportStack` (Phase 3) | The AI-agent security profiles, the customer-managed views, the eSIM step-by-step guide flow, and the Lex V2 Q-in-Connect passthrough bot |
| `cdk deploy CX-TELCO-AGENTS` | `AiAgentsStack` (Phase 4) | The Orchestration AI prompts and the three AI agents (self-service voice + chat, agent-assist) |
| `cdk deploy CX-TELCO-FLOWS` | `ContactFlowsStack` (Phase 5) | The escalation handoff view, screen-pop flow, the escalate + set-customer-session flow modules, and the Spanish self-service inbound flow |

> Phase 6 (website) is the remaining planned stack and will register in `app.py`
> as an additional `CX-TELCO-*` stack.

---

## What Is Deployed

**Phase 1 — `CX-TELCO-MCP`**
- **DynamoDB tables** for `accounts`, `plans`, and `lines` (on-demand, seeded with sample data at deploy time).
- **Lambda functions** backing the API and Connect: `accounts`, `plans`, `lines`, and `ai_session`.
- **REST API** (API Gateway) for telco operations, protected by an API key stored in **Secrets Manager**.
- **AgentCore Gateway** (Bedrock) that re-exposes the REST API as an **MCP server**, with an **API-key credential provider** and an inline OpenAPI target.
- **Amazon Connect integrations**: registers the gateway as an **MCP server application** on the Connect instance, and associates the `plans` + `ai_session` Lambdas (`LAMBDA_FUNCTION`).

**Phase 2 — `CX-TELCO-KB`**
- **KMS key + S3 bucket** holding the HTML knowledge articles (uploaded by CDK under `telco/<lang>/`).
- **AppIntegrations DataIntegration** + **EXTERNAL Q in Connect knowledge base** that crawls the bucket.
- **Assistant association** binding the KB to the Q in Connect AI Agents domain so an agent's Retrieve tool can query it.

**Phase 3 — `CX-TELCO-CONNECT-SUPPORT`**
- **AI-agent security profiles** (self-service + agent-assist): least-privilege `Wisdom.View` + `CustomViews.Access` (the guides permission), plus the MCP tool grant built at deploy time from the gateway id.
- **Customer-managed views** (`AWS::Connect::View`): the new-line guided form and the eSIM activation guide.
- **eSIM guide contact flow** (`AWS::Connect::View` guide + flow). The `AMAZON_CONNECT_GUIDE` content association that binds the flow to the `esim-activacion` KB content is created post-deploy by `knowledge_bases/associate_esim_guide.py` (the content ids are post-ingestion values), not by the stack.
- **Lex V2 Q-in-Connect passthrough bot** (`AWS::Lex::Bot`): a single `AMAZON.QInConnectIntent` wired to the AI Agents assistant, 3 locales (en_US/es_US/pt_BR) on Nova Sonic v2 unified speech, carrying the case-sensitive `AmazonConnectEnabled=True` tag. To keep deploys fast, the locales are **not** auto-built and no version/alias is created in CloudFormation — the stack publishes the bot's built-in **TestBotAlias** ARN (`.../bot-alias/<botId>/TSTALIASID`) to SSM. After deploy, build the three locales once in the Lex/Connect console; the TestBotAlias then points at DRAFT and the inbound flow can use it.

**Phase 4 — `CX-TELCO-AGENTS`**
- **Orchestration AI prompts** (`AWS::Wisdom::AIPrompt`): the prompt bodies pulled from the live Q in Connect domain, one per agent surface.
- **Three AI agents** (`AWS::Wisdom::AIAgent`, type `MANUAL`/orchestration): self-service **voice** and **chat** (KB Retrieve + the 9 AgentCore MCP tools + Escalate/Complete; chat adds the new-line guide), and **agent-assist** (Retrieve + MCP surface only). Per-agent models are kept as authored (voice/chat on Haiku 4.5, assist on Sonnet). The `<sources>` citation behavior is enforced by the system Retrieve tool, not the orchestration prompt.
- Consumes `MCP_TOOL_PREFIX` (Phase 1) for the MCP tool ids and `KB_ASSOC_ID` (Phase 2) for the Retrieve binding; publishes the three agent ARNs for the flows. Security-profile assignment to the agents is a **manual** post-deploy step.

**Phase 5 — `CX-TELCO-FLOWS`**
- **Escalation handoff view** (`AWS::Connect::View`): the agent screen-pop rendered on accept.
- **Screen-pop contact flow** (`AWS::Connect::ContactFlow`): registers the handoff view as the `DefaultAgentUI`.
- **Flow modules** (`AWS::Connect::ContactFlowModule`): `escalate-to-agent` (sets the screen-pop hook, sets the target queue, transfers) and `set-customer-session-telco` (classifies the endpoint, looks the customer up via the ai_session Lambda, writes the Q in Connect session).
- **Inbound self-service flow** (`AWS::Connect::ContactFlow`): the Spanish voice/chat entry flow that creates the Wisdom session, binds the Lex bot + the voice/chat/assist agents, drives the new-line guided form, and escalates to a human.
- **BasicQueue lookup** (`connect:ListQueues` custom resource): resolves the instance's queue ARN by name at deploy time (queue ids are per-instance), so the flows transfer to a valid queue with no hard-coded id. Consumes the ai_session Lambda ARN (Phase 1), the new-line view ARN + Lex bot alias ARN (Phase 3), and the three agent ARNs (Phase 4).

**Shared mechanism** — producer stacks publish a few ids/ARNs to **SSM Parameter Store** (`/agentic-cx-telco/...`); consumer stacks read them at deploy time. Deploy order is enforced with `stack.add_dependency` (ordering only — no `Fn::ImportValue`). Secrets never go on the bus (the API key stays in Secrets Manager).

---

## Configuration

All configuration is flat module-level constants in `config.py` (no secrets; AWS
credentials resolve from your local profile/SSO at deploy time). Key values:

- **Connect identity** — `INSTANCE_ID`, `INSTANCE_ALIAS` (builds the gateway's OIDC discovery URL); `HAS_REAL_INSTANCE` gates instance-bound resources.
- **Naming** — `PROJECT_NAME`, `API_NAME`, `API_STAGE_NAME`, `GATEWAY_NAME`, DynamoDB table/index names.
- **Gateway audience** — none to configure: the gateway is created with a placeholder audience and an `UpdateGateway` custom resource patches `allowedAudience` to the gateway's own id in a single deploy.
- **Knowledge base** — `KB_NAME`, `KB_ENTRIES_DIR`, `KB_BUCKET_PREFIX`, `KB_CONTENT_TAGS`, `ASSISTANT_ID`.
- **Security profiles** — `AI_AGENT_SECURITY_PROFILE_NAME`, `AI_AGENT_SECURITY_PROFILE_PERMISSIONS` (`Wisdom.View` + `CustomViews.Access`), `AI_AGENT_ASSIST_SECURITY_PROFILE_NAME`, `BUILD_AI_AGENT_MCP_GRANT`.
- **Views & guide** — `NEWLINE_VIEW_NAME` / `NEWLINE_VIEW_CONTENT`, `ESIM_GUIDE_VIEW_NAME` / `ESIM_GUIDE_VIEW_CONTENT`, `FLOW_ESIM_GUIDE`, `ESIM_GUIDE_FLOW_NAME` / `ESIM_GUIDE_CONTENT_MATCH` (used by the post-deploy `associate_esim_guide.py` script).
- **Lex bot** — `LEX_BOT_NAME` (the Q-in-Connect passthrough bot created in Phase 3; its TestBotAlias ARN is published to SSM for the inbound flow).
- **AI agents** — `BUILD_AI_AGENTS` / `BUILD_AGENT_ASSIST`, `AI_AGENT_LOCALE`, the per-agent `AI_AGENT_*_PROMPT` paths and `AI_AGENT_*_MODEL` ids. Agents are native `AWS::Wisdom::AIAgent`; tool input schemas omit `maxLength` (the provider stringifies it into an invalid JSON Schema and breaks orchestration).
- **Contact flows** — `FLOW_*` JSON paths, `ESCALATION_HANDOFF_VIEW_*`, and `BASIC_QUEUE_NAME` (resolved at deploy time by the lookup custom resource) with optional `BASIC_QUEUE_ID` to pin a specific queue.
- **MCP tool wiring** — `AI_AGENT_MCP_TARGET`, `AI_AGENT_MCP_OPERATIONS` (used to build the per-tool grant ids; the gateway id itself comes from SSM).

### SSM parameters (the cross-stack contract)

Defined once in `shared/ssm_names.py`. Only values that genuinely cross a stack
boundary are published; everything else stays a CfnOutput.

| Parameter | Producer | Consumed by | Purpose |
|---|---|---|---|
| `/agentic-cx-telco/agentcore/gateway-id` | `CX-TELCO-MCP` | Phase 3 | bare gateway id (security-profile MCP namespace + Connect JWT audience) |
| `/agentic-cx-telco/agentcore/mcp-tool-prefix` | `CX-TELCO-MCP` | Phase 4 | `gateway_<id>__<target>___` prefix for agent MCP tool ids |
| `/agentic-cx-telco/agentcore/lambda/plans-arn` | `CX-TELCO-MCP` | Phase 5 | plans Lambda ARN (for contact flows) |
| `/agentic-cx-telco/agentcore/lambda/ai-session-arn` | `CX-TELCO-MCP` | Phase 5 | ai_session Lambda ARN (for contact flows) |
| `/agentic-cx-telco/kb/knowledge-base-id` | `CX-TELCO-KB` | script | KB id (read by `knowledge_bases/associate_esim_guide.py` for the eSIM content association) |
| `/agentic-cx-telco/kb/assistant-association-id` | `CX-TELCO-KB` | Phase 4 | KB↔assistant association id (agent Retrieve binding) |
| `/agentic-cx-telco/connect/security-profile-selfservice-id` | `CX-TELCO-CONNECT-SUPPORT` | manual | self-service AI-agent security profile id (for the manual agent assignment) |
| `/agentic-cx-telco/connect/security-profile-assist-id` | `CX-TELCO-CONNECT-SUPPORT` | manual | agent-assist security profile id (for the manual agent assignment) |
| `/agentic-cx-telco/connect/view-newline-qualified-arn` | `CX-TELCO-CONNECT-SUPPORT` | Phase 5 | new-line form view ARN (inbound flow ShowView) |
| `/agentic-cx-telco/connect/lex-bot-alias-arn` | `CX-TELCO-CONNECT-SUPPORT` | Phase 5 | Lex bot TestBotAlias ARN (`.../TSTALIASID`) for the inbound flow's Lex blocks |
| `/agentic-cx-telco/agents/voice-arn` | `CX-TELCO-AGENTS` | Phase 5 | self-service voice AI-agent ARN (inbound flow voice binding) |
| `/agentic-cx-telco/agents/chat-arn` | `CX-TELCO-AGENTS` | Phase 5 | self-service chat AI-agent ARN (inbound flow chat binding) |
| `/agentic-cx-telco/agents/assist-arn` | `CX-TELCO-AGENTS` | Phase 5 | agent-assist AI-agent ARN (inbound flow assist binding) |

---

## Deploy

```bash
source .venv/bin/activate
pip install -r requirements.txt

# synth (verification gate) — cdk.json runs `python3 app.py`, so the active venv
# is the interpreter. Use your installed CDK CLI.
cdk synth

# Phase 1 + Phase 2 — independent, deploy in any order
cdk deploy CX-TELCO-MCP --profile connect-industry
cdk deploy CX-TELCO-KB  --profile connect-industry

# Phase 3 — depends on Phase 1 (gateway id) and Phase 2 (kb id)
cdk deploy CX-TELCO-CONNECT-SUPPORT --profile connect-industry

# Phase 4 — depends on Phase 1 (MCP tool prefix) and Phase 2 (KB association)
cdk deploy CX-TELCO-AGENTS --profile connect-industry

# Phase 5 — depends on Phase 1 (ai_session Lambda), Phase 3 (view + Lex alias),
# and Phase 4 (agent ARNs)
cdk deploy CX-TELCO-FLOWS --profile connect-industry
```

After deploying the agents (Phase 4), assign the Phase 3 security profiles to
the AI agents — this is a **manual** post-deploy step (there is no native CFN
resource for `connect:AssociateSecurityProfiles` with `EntityType=AI_AGENT`, and
the project no longer carries a custom resource for it):

1. In the **Amazon Connect admin website**, open **AI agents** (Q in Connect).
2. For each agent — `telco-selfservice-voice-es`, `telco-selfservice-chat-es`,
   `telco-agent-assist-es` — assign a security profile:
   - voice + chat → `telco-selfservice-ai-agent-iac`
   - agent-assist → `telco-agent-assist-iac`
3. For **agent-assist**, the human agents who use the assistant panel must also
   carry the same permissions (`Wisdom.View`, `CustomViews.Access`, and the MCP
   tool grant) — tool calls authorize against the intersection of the AI agent's
   and the human agent's profiles.

The profile ids are also published to SSM
(`/agentic-cx-telco/connect/security-profile-selfservice-id` and
`.../security-profile-assist-id`) for reference / scripting.

After `CX-TELCO-KB` deploys and the KB finishes its first sync, tag the content
so the Retrieve tool can find it:

```bash
python knowledge_bases/tag_kb_content.py --wait --expect 21 --kb-id <kb-id from output> --profile connect-industry
```

To wire the eSIM step-by-step guide to its knowledge article, run the
post-deploy association script after the KB finishes its sync. It resolves the
KB id (from SSM), resolves the guide flow ARN by name, finds the `esim-*`
content by title, and creates the `AMAZON_CONNECT_GUIDE` association
idempotently — no content ids to hand-maintain:

```bash
python knowledge_bases/associate_esim_guide.py --profile connect-industry
# preview first with --dry-run
```

(The `esim-activacion` / `esim-activation` titles are the per-language copies;
`--match` narrows the substring if you only want one.)

After `CX-TELCO-CONNECT-SUPPORT` deploys, build the Lex bot's three locales so
its TestBotAlias goes live for the inbound flow (the locales are intentionally
not auto-built to keep the deploy fast):

1. Open **`telco-qconnect-bot-v2`** (the `LEX_BOT_NAME`) in the Amazon Lex V2 console.
2. Build each locale — `en_US`, `es_US`, `pt_BR`.
3. The built-in **TestBotAlias** (`TSTALIASID`) then serves the DRAFT version; the
   `CX-TELCO-FLOWS` inbound flow already binds this alias (resolved from SSM).
