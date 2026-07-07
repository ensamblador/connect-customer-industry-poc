> 🌎 **Español:** [ver la versión en español (`instructions.md`)](instructions.md)

# Deployment Instructions — Connect Customer Industry PoC

End-to-end setup for the CDK apps in this repo:

- **`general-localization/`** → stack **`CX-LANG-UTILS`** (localized queue flow + per-locale Q in Connect utility prompts/agents, plus the centralized AI-agent CloudWatch logging).
- **`agentic-cx-telco/`** → six **`CX-TELCO-*`** stacks (telco MCP backend, knowledge base, Connect support resources, AI agents, contact flows, website).
- **`agentic-cx-bank/`** → six **`CX-BANCO-*`** stacks (retail-banking MCP backend, knowledge base, Connect support resources, AI agents, contact flows, website).

Steps marked **[MANUAL]** are done by hand in a console; **[SCRIPT]** steps run a helper script; everything else is `cdk deploy`. Keep a single AWS account + region for the whole walkthrough — the helper scripts and the SSM cross-stack contract resolve against whatever your active profile/region point to.

> The telco and bank apps are structurally identical (both re-theme the same reference architecture). This guide walks through telco end-to-end; the **[Bank app](#8-bank-app-cx-banco)** section at the end lists only what differs.

---

## 0. Prerequisites

- Node.js + npm (for the CDK CLI and the Vite website build).
- Python 3 with a virtualenv per CDK app (`agentic-cx-telco/.venv`, `agentic-cx-bank/.venv`, `general-localization/.venv`).
- AWS credentials available in your environment (e.g. `AWS_PROFILE` / SSO). The helper scripts use plain `boto3.client(...)` and inherit the region/profile from your shell — they do **not** take `--profile`/`--region`.
- AWS CDK CLI (`npm i -g aws-cdk` or use `npx cdk`).

```bash
# once per AWS account/region
cdk bootstrap
```

---

## 1. [MANUAL] Create the Amazon Connect instance + Q in Connect AI assistant

1. In the **Amazon Connect** console, create (or pick) a Connect **instance**. Note its **instance id** and **instance alias**.
2. Create a **Q in Connect** domain / **AI assistant** (the "AI agents domain"). Note its **assistant id**.

Then update config in every app so they target the live instance:

- `agentic-cx-telco/config.py` and `agentic-cx-bank/config.py` → set `INSTANCE_ALIAS`, `INSTANCE_ID`, `ASSISTANT_ID`.
  - `HAS_REAL_INSTANCE` flips to `True` automatically once `INSTANCE_ALIAS` is no longer the placeholder; it gates every instance-bound resource.
- `general-localization/config.py` → set `INSTANCE_ID`, `ASSISTANT_ID` (same instance/assistant).

---

## 2. Deploy `general-localization` (`CX-LANG-UTILS`)

```bash
cd general-localization
source .venv/bin/activate
pip install -r requirements.txt
cdk deploy
```

**Deploys:**
- **Localized customer-queue contact flow** (`CUSTOMER_QUEUE`) that branches on the contact's `LanguageCode` and plays a per-language hold message + TTS voice (en/es/pt, default English). The queue hold-music prompt is resolved by name at deploy time (`connect:ListPrompts`).
- **`init-flow-es-v2` contact flow module** — enables flow logging, sets the localized queue flow as the `CustomerQueue` event hook, and configures per-channel recording/analytics.
- **Per-locale Q in Connect AI prompts + utility AI agents** for every enabled non-English locale in `config.LOCALES` (currently `es_US`): four prompts (query reformulation, answer generation, intent labeling, note taking) feeding three agents (Answer Recommendation, Manual Search, Note Taking).
- **Centralized AI-agent CloudWatch logging** (gated by `config.ENABLE_AGENT_LOGS`) — the single `EVENT_LOGS` delivery from the shared assistant to CloudWatch Logs lives **only** here. Because the `ASSISTANT_ID` is shared across the telco and bank apps and CloudWatch Logs allows only one delivery source per resource, this logging is owned exclusively by `CX-LANG-UTILS`; the industry stacks carry no logging resources.
- Publishes the queue flow + init module + agent ARNs to **SSM** and emits them as **CfnOutputs**.

### 2a. [MANUAL] Set the localized utility agents as the domain defaults

The three localized utility agents are created in the assistant but aren't wired as the **default AI agents** automatically. In the **Amazon Connect** console → **AI agents** (your Q in Connect domain) → **Default AI agents**, assign them per use case (then **Save**):

| Use case | Default agent |
|---|---|
| Answer Recommendation | `localized-answer-recommendation-es_US` |
| Manual Search | `localized-manual-search-es_US` |
| Note Taking | `localized-note-taking-es_US` |

Leave the other use cases (Self Service, Email *, Case Summarization, Agent Assistance) on their existing/default values. Repeat for every additional locale you enable in `config.LOCALES`.

---

## 3. Build the website assets (before deploying the telco app)

```bash
cd agentic-cx-telco/website
npm install
npm run build      # produces website/dist, consumed by CX-TELCO-WEBSITE
```

`config.BUILD_WEBSITE` gates the website stack — it must find `website/dist` at synth time. (You'll rebuild + redeploy the site again in step 7 after wiring the chat widget.)

---

## 4. Deploy the `agentic-cx-telco` stacks

```bash
cd agentic-cx-telco
source .venv/bin/activate
pip install -r requirements.txt
cdk synth                 # verification gate
cdk deploy --all          # or deploy phase by phase (order below)
```

Phase order (enforced by `add_dependency`, ordering-only — values cross stacks through SSM, never `Fn::ImportValue`):

| Order | Stack | What it deploys |
|---|---|---|
| 1 | **`CX-TELCO-MCP`** | DynamoDB tables (`accounts`/`plans`/`lines`) + seed data, the Lambda backend (`accounts`/`plans`/`lines`/`ai_session`), the Telco REST API (API key in Secrets Manager), the **AgentCore MCP gateway** (re-exposes the REST API as MCP tools, with API-key credential provider + inline OpenAPI target), and the Connect integrations (registers the gateway as an MCP server app + associates the `plans`/`ai_session` Lambdas). |
| 1 | **`CX-TELCO-KB`** | KMS key + S3 bucket holding the HTML KB articles (es/pt/en), an AppIntegrations DataIntegration, the **EXTERNAL Q in Connect knowledge base** that crawls the bucket, and the assistant association binding the KB to the AI agents domain. *Independent of MCP — can deploy in parallel.* |
| 2 | **`CX-TELCO-CONNECT-SUPPORT`** | AI-agent **security profiles** (self-service + agent-assist, `Wisdom.View` + `CustomViews.Access` + the deploy-time MCP tool grant), **customer-managed views** (new-line guided form, eSIM activation guide), the **eSIM guide contact flow**, and the **Lex V2 Q-in-Connect passthrough bot** (`telco-qconnect-bot-v2`, 3 locales, Nova Sonic v2, TestBotAlias ARN published to SSM). |
| 3 | **`CX-TELCO-AGENTS`** | The **Orchestration AI prompts** and the **three AI agents** — self-service **voice** + **chat** (KB Retrieve + 9 AgentCore MCP tools + Escalate/Complete; chat adds the new-line guide) and **agent-assist** (Retrieve + MCP surface). Consumes the MCP tool prefix (Phase 1) and KB association id (Phase 2). |
| 4 | **`CX-TELCO-FLOWS`** | The escalation **handoff view**, the **screen-pop flow** (registers the view as `DefaultAgentUI`), the **flow modules** (`escalate-to-agent`, `set-customer-session-telco`), and the **Spanish self-service inbound flow** (creates the Wisdom session, binds the Lex bot + the three agents, drives the new-line guided form, escalates to a human). Resolves the BasicQueue ARN by name at deploy time. |
| 5 | **`CX-TELCO-WEBSITE`** | The static "Latam Telco" site → private **S3 + CloudFront (OAC)**, hosting the Amazon Connect **chat widget** and a demo data viewer at **`/datos`** (a Lambda that renders the Phase 1 DynamoDB tables). Ordered after MCP (ordering-only). |

---

## 5. [SCRIPT] Post-deploy: tag KB content + wire the eSIM guide

Run after `CX-TELCO-KB` finishes its first **async** sync (these can't be CloudFormation resources because the crawler creates new, untagged content ids on every sync). From `agentic-cx-telco/`, with the venv active and your AWS profile/region set in the environment:

```bash
# 1) Tag every content item so the agents' Retrieve filter can find it.
#    kb-id resolves from SSM automatically; --wait polls until ingestion is ACTIVE.
python knowledge_bases/tag_kb_content.py --wait --expect 21

# 2) Bind the eSIM step-by-step guide flow to its KB article (idempotent).
python knowledge_bases/associate_esim_guide.py        # add --dry-run to preview
```

> If `--expect 21` doesn't match your actual ingested count, adjust it (or drop `--expect`) or `--wait` will time out.

---

## 6. [MANUAL] Post-deploy console steps

These have no native CloudFormation resource and must be done by hand:

1. **Attach the security profile to each AI agent and publish a new version.** In the **Amazon Connect** admin website → **AI agents** (your Q in Connect domain), open each agent, **attach its security profile**, then **Save and Publish a new version**:
   - `telco-selfservice-voice-es` and `telco-selfservice-chat-es` → `telco-selfservice-ai-agent-iac`
   - `telco-agent-assist-es` → `telco-agent-assist-iac`
   - For **agent-assist**, the human agents using the assistant panel must also carry the same permissions (`Wisdom.View`, `CustomViews.Access`, MCP tool grant) — tool calls authorize against the intersection of the AI agent's and human agent's profiles. (Profile ids are also published to SSM for scripting.)

   > **Required — this is what authorizes the MCP tool calls.** The AgentCore MCP tools are granted through the security profile, and the running agent uses the **published version**. If the profile is not attached (or you edited it but did not publish a new version), MCP tool calls fail at invocation with `Target entity not found` even though the gateway/target and backend REST API are healthy. After attaching the profile, always **publish a new version** and confirm the flow/binding points at that version.

2. **Take control of the bot from Amazon Connect (toggle Lex Bot Management) — do this _before_ building the locales.** Because the bot is created on the **Amazon Lex** side (via CDK), the Connect instance doesn't refresh its Lex Bot Management link automatically, so the bot won't be selectable/editable inside Connect flows until you toggle the feature. In the **Amazon Connect** console → your instance → **Flows** → **Amazon Lex Bots** section:

   1. Untick **Enable Lex Bot Management in Amazon Connect** → **Save** (disable → save).
   2. Tick **Enable Lex Bot Management in Amazon Connect** again → **Save** (enable → save).

   Connect creates the **service role** and the **service-linked role** for you as part of this toggle, and `telco-qconnect-bot-v2` becomes visible to the instance. (You do **not** need to create the Lex service-linked role by hand.)

3. **Build the Lex bot locales** (Amazon Lex V2 console): open `telco-qconnect-bot-v2` and build `en_US`, `es_US`, `pt_BR`. They're intentionally not auto-built to keep deploys fast; once built, the TestBotAlias (`TSTALIASID`) serves DRAFT and the inbound flow (already bound via SSM) works.

   > **Enable the locales on the TestBotAlias too.** After building, make sure each locale (`en_US`/`es_US`/`pt_BR`) is enabled on the **TestBotAlias**. If a locale isn't enabled on the alias the flow uses, chat fails at the `ConnectParticipantWithLexBot` step with `The BotAliasId TSTALIASID does not have Language <locale> enabled`. The bank app wires this automatically with a small custom resource; for telco confirm it in the console (Aliases → TestBotAlias → Languages) or via `aws lexv2-models update-bot-alias`.

---

## 7. [MANUAL] Wire the chat widget into the website

1. In the **Amazon Connect** console, create a **chat communications widget**. When creating it, add your **approved origins** so the widget is allowed to load:
   - `http://localhost` (and/or `http://localhost:<port>`) for local development.
   - The CloudFront domain from the website stack output, e.g. `https://{id}.cloudfront.net` (the `WebsiteDistributionDomainName` / `WebsiteDataViewerPath` output of `CX-TELCO-WEBSITE` / `CX-BANCO-WEBSITE`).

   > The widget will silently fail to load on any origin not in this list. Since the CloudFront domain isn't known until the website stack deploys, you typically create the widget, deploy the site, then come back and add the real `*.cloudfront.net` origin (a custom domain works too once configured).
2. Open `agentic-cx-telco/website/index.html` and **update the Connect widget**: replace the content **between** these two markers with your generated widget snippet, as is — leave the markers in place:

   ```html
   <!--REPLACE WITH CONNECT WIDGET AS IS (BELOW THIS LINE)-->
   [HERE IS YOUR WIDGET CONTENT]
   <!--END OF CONNECT WIDGET (ABOVE THIS LINE)-->
   ```

   > **Passing the logged-in email as a contact attribute.** The site registers `window._connectContactAttrs` as the widget's `contactAttributes` object **once**, then mutates that same object reference on login/logout. Keep that pattern: if you build a brand-new object on every `contactAttributes` call the widget never sees the post-login email, and the customer lookup can't personalize the contact.

3. Rebuild and redeploy the site:

```bash
cd agentic-cx-telco/website
npm run build
cd ..
cdk deploy CX-TELCO-WEBSITE
```

---

## 8. Bank app (`CX-BANCO-*`)

The bank app (`agentic-cx-bank/`) mirrors telco step-for-step. Deploy it the same way, substituting the names below. **It has one extra prerequisite: `CX-LANG-UTILS` must already be deployed**, because the bank inbound flow consumes the external `/flows/init/es` SSM parameter (the `init-flow-es-v2` module) published by `general-localization` as its start module.

Deploy order: **`CX-BANCO-MCP` → `CX-BANCO-KB` → `CX-BANCO-CONNECT-SUPPORT` → `CX-BANCO-AGENTS` → `CX-BANCO-FLOWS` → `CX-BANCO-WEBSITE`** (Phases 1 and 2 are mutually independent).

What differs from telco:

| Concept | Telco | Bank |
|---|---|---|
| Backend domain | accounts / plans / lines | accounts / products / cards |
| DynamoDB tables | `accounts` / `plans` / `lines` | `banco-accounts` / `banco-products` / `banco-cards` |
| REST API / gateway | `telco-api` | `banco-api` / `banco-mcp-server` |
| Guided form + guide | new-line form + eSIM activation guide | card-request form + activate-card guide |
| Lex bot | `telco-qconnect-bot-v2` | `banco-qconnect-bot-v2` |
| Security profiles | `telco-selfservice-ai-agent-iac` / `telco-agent-assist-iac` | `banco-selfservice-ai-agent` / `banco-agent-assist-iac` |
| AI agents | `telco-selfservice-voice-es` / `-chat-es` / `telco-agent-assist-es` | `banco-selfservice-voice-es` / `-chat-es` / `banco-agent-assist-es` |
| Website | "Latam Telco" | "Latam Banco" |
| Guide-baking script | `associate_esim_guide.py` | `associate_activate_card_guide.py` |
| Retrieve segmentation | `industry=telco` | `industry=bank` AND `language=es` |

Bank post-deploy scripts (after `CX-BANCO-KB` syncs):

```bash
cd agentic-cx-bank
source .venv/bin/activate
python knowledge_bases/tag_kb_content.py --wait --expect 21
python knowledge_bases/associate_activate_card_guide.py        # add --dry-run to preview
```

Then repeat the same **[MANUAL]** console steps from sections 6 and 7 (attach + publish security profiles, toggle Lex Bot Management, build + enable the three Lex locales on the TestBotAlias, and wire the chat widget into `agentic-cx-bank/website/index.html`).

> The bank Lex bot's TestBotAlias locale enablement is handled automatically by a custom resource in `CX-BANCO-CONNECT-SUPPORT`, so chat works without the manual alias-locale toggle. You still need to **build** the three locales in the Lex console.

---

## Manual / script steps at a glance

| # | Type | Step |
|---|---|---|
| 0 | manual | `cdk bootstrap` (per account/region) |
| 1 | manual | Create Connect instance + Q in Connect assistant; update `config.py` in every app |
| 2 | manual | Set localized utility agents as domain defaults (Answer Recommendation / Manual Search / Note Taking) |
| 3 | manual | `npm install && npm run build` the website before each app's deploy |
| 5 | script | `tag_kb_content.py --wait` (KB id auto-resolved from SSM) |
| 5 | script | `associate_esim_guide.py` (telco) / `associate_activate_card_guide.py` (bank) |
| 6 | manual | Attach the Phase 3 security profiles to the three AI agents (authorizes the MCP tools), then **publish a new version** — without this, tool calls fail with `Target entity not found` |
| 6 | manual | Take control of the bot in Connect: Flows → toggle Lex Bot Management off+save, on+save (creates the roles) — do this **before** building the locales |
| 6 | manual | Build the Lex bot's `en_US` / `es_US` / `pt_BR` locales and confirm they are enabled on the TestBotAlias |
| 7 | manual | Create chat widget (add `http://localhost` + the `https://{id}.cloudfront.net` output as **approved origins**), paste it between the widget markers in `website/index.html`, rebuild + redeploy website |

> Full per-stack detail, the SSM cross-stack contract, and config reference live in each app's `README.md` (`README-en.md` for English).
