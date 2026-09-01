# Deployment instructions — Connect Customer Industry PoC

> 🌐 **Languages:** [Español](./instructions.md) · **English** (this file)

End-to-end setup for the CDK apps in this repository:

- **`general-localization/`** → the **`CX-LANG-UTILS`** stack (localized queue flow + per-locale Q in Connect utility prompts/agents, plus the centralized CloudWatch logging for the AI agents).
- **`agentic-cx-{industry}/`** → six **`CX-{INDUSTRY}-*`** stacks (the industry's MCP backend, knowledge base, Connect supporting resources, AI agents, contact flows, website).

> **Available industries:** `telco`, `banco`, `airline`. This guide is **generic**: substitute `{industry}` with one of them (and `{INDUSTRY}` with `TELCO`, `BANCO` or `AIRLINE` in the stack names) depending on the app you are deploying. All industry apps are structurally identical (they re-theme the same reference architecture); only the domain data changes (KB, tables, guide, site). Deploy `CX-LANG-UTILS` **once** (step 2) and then repeat steps 3–7 for each industry you want.

Steps marked **[MANUAL]** are done by hand in a console; steps marked **[SCRIPT]** run a helper script; everything else is `cdk deploy`. Use a single AWS account + region for the whole walkthrough — the helper scripts and the SSM contract between stacks resolve against the profile/region active in your shell.

> **Guide association script — unified.** In every app, the step-by-step guide (which Q in Connect surfaces when the customer mentions a specific topic) is bound to its KB article by a **single shared script, `knowledge_bases/associate_guide.py`**, identical across all projects. The script resolves the guide flow's name and the content match text from the **standard** `GUIDE_FLOW_NAME` and `GUIDE_CONTENT_MATCH` constants in each app's `config.py`, so it **automatically makes the associations that belong to that industry** — associating every per-language copy (es/pt/en) of the article, idempotently.

---

## 0. Prerequisites

- Node.js + npm (for the CDK CLI and the Vite site build).
- Python 3 with a virtualenv **per CDK app** (`agentic-cx-{industry}/.venv`, `general-localization/.venv`). Create it with `python3 -m venv .venv` inside each app before the first deployment.
- AWS credentials available in your environment (e.g. `AWS_PROFILE` / SSO). The helper scripts use `boto3.client(...)` directly and inherit the region/profile from your shell — they do **not** accept `--profile`/`--region`.
- The three **Connect identity environment variables** exported in your shell — `INSTANCE_ALIAS`, `INSTANCE_ID`, `ASSISTANT_ID` (see step 0a).
- The AWS CDK CLI (`npm i -g aws-cdk`, or use `npx cdk`).

```bash
# once per AWS account/region — use the explicit aws://<account-id>/<region> form
cdk bootstrap #optional account id and region: cdk bootstrap aws://123456789012/us-east-1
```

Create the virtualenv for each CDK app you are going to deploy (once per app):

```bash
# general-localization
cd general-localization
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ..
deactivate

# one per industry: telco / banco / airline
cd agentic-cx-{industry}
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ..
deactivate
```

### 0a. Connect identity via environment variables

The Connect instance and assistant ids **do not live in the repository**: all four `config.py` files read them from the environment as **required** variables and raise `ConfigError` on import if any is missing. This keeps account-specific values out of the repo (the alias embeds your account number) and makes a forgotten `source` stop the deploy with an error naming the variable, instead of synthesizing a half-configured stack or deploying against the wrong instance.

The three variables are identical for all four apps (same instance, same assistant), so a single `.env` at the repo root configures everything. `.env` is gitignored; `.env.example` is the committed template:

```bash
cp .env.example .env
# edit .env with your alias + the two UUIDs (step 1)
```

`.env` carries `export` on every line, so a single `source` per terminal is enough, before any `cdk` command or helper script:

```bash
cd agentic-cx-{industry}
source ../.env          # equivalent: set -a; source ../.env; set +a

# quick check
echo $INSTANCE_ALIAS $INSTANCE_ID $ASSISTANT_ID
```

> To avoid re-sourcing in every new terminal, export them from your shell profile or use [direnv](https://direnv.net/), which loads `.env` automatically when you enter the directory.

> **The tests do not need these variables.** Each app ships a root `conftest.py` that fills in dummy values when they are unset (the tests only synthesize templates, they never call AWS), so `pytest` works in a clean shell. A real exported value still wins.

---

## 1. [MANUAL] Create the Amazon Connect instance + the Q in Connect AI assistant

1. In the **Amazon Connect** console, create (or pick) a Connect **instance**. Note its **instance id** and its **instance alias**.
2. Create a **Q in Connect** domain / **AI assistant** (the "AI agents domain"). Note its **assistant id**.

Then put those three values in the repo-root `.env` (they are **not** edited in `config.py` — see step 0a):

```bash
export INSTANCE_ALIAS=my-connect-alias        # subdomain of https://<alias>.my.connect.aws
export INSTANCE_ID=00000000-0000-0000-0000-000000000000
export ASSISTANT_ID=00000000-0000-0000-0000-000000000000
```

To look them up from the CLI:

```bash
aws connect list-instances      # -> Id (INSTANCE_ID) + Alias (INSTANCE_ALIAS)
aws qconnect list-assistants    # -> assistantId (ASSISTANT_ID)
```

All four apps (`general-localization` + the three industry apps) read these same three variables, so one root `.env` configures them all. Every **resource name** is prefixed with its industry (`telco-*` / `banco-*` / `airline-*`), so it never collides with another industry's on the shared instance.

> `INSTANCE_ALIAS` also builds the `OIDC_DISCOVERY_URL` for the AgentCore MCP gateway's inbound JWT authorizer, which is why the alias is needed and not just the id.

---

## 2. Deploy `general-localization` (`CX-LANG-UTILS`)

```bash
cd general-localization
source ../.env                 # INSTANCE_ID + ASSISTANT_ID (step 0a)
source .venv/bin/activate
pip install -r requirements.txt
cdk deploy
cd ..
```

**Deploys:**
- A **localized customer-queue contact flow** (`CUSTOMER_QUEUE`) that branches on the contact's `LanguageCode` and plays a hold message + TTS voice per language (en/es/pt, English by default). The hold-music prompt is resolved by name at deploy time (`connect:ListPrompts`).
- The **`init-flow-es-v2` contact flow module** — enables flow logging, sets the localized queue flow as the `CustomerQueue` event hook, and configures recording/analytics per channel.
- **Per-locale Q in Connect AI prompts + utility agents** for every non-English locale enabled in `config.LOCALES` (currently `es_US`): four prompts (query reformulation, answer generation, intent labeling, note taking) feeding three agents (Answer Recommendation, Manual Search, Note Taking).
- **Centralized CloudWatch logging for the AI agents** (controlled by `config.ENABLE_AGENT_LOGS`) — the single `EVENT_LOGS` delivery from the shared assistant to CloudWatch Logs lives **only** here. Because `ASSISTANT_ID` is shared across all industry apps, and CloudWatch Logs allows only one delivery source per resource, this logging is owned exclusively by `CX-LANG-UTILS`; the industry stacks carry no logging resources.
- Publishes the queue flow + the init module + the agent ARNs to **SSM** and emits them as **CfnOutputs**.

### 2a. [MANUAL] Set the localized utility agents as the domain defaults

The three localized utility agents are created on the assistant but are not wired up as **default AI agents** automatically. In the **Amazon Connect** console → **AI agents** (your Q in Connect domain) → **Default AI agents**, assign them per use case (then **Save**):

| Use case | Default agent |
|---|---|
| Answer Recommendation | `localized-answer-recommendation-es_US` |
| Manual Search | `localized-manual-search-es_US` |
| Note Taking | `localized-note-taking-es_US` |

Leave the other use cases (Self Service, Email *, Case Summarization, Agent Assistance) at their existing/default values. Repeat for each additional locale you enable in `config.LOCALES`.

---

> **From here on, steps 3–7 apply to any industry.** Substitute `{industry}` with `telco`, `banco` or `airline`, and `{INDUSTRY}` with `TELCO`, `BANCO` or `AIRLINE` (in the stack names) depending on the app you are deploying. Repeat these steps for each industry.

## 3. Build the website assets (before deploying the app)

```bash
cd agentic-cx-{industry}/website
npm install
npm run build      # produces website/dist, consumed by CX-{INDUSTRY}-WEBSITE
cd ..
```

`config.BUILD_WEBSITE` controls the site stack — it must find `website/dist` at synth time. (You will rebuild + redeploy the site in step 7, after wiring the chat widget.)

---

## 4. Deploy the `agentic-cx-{industry}` stacks

**Prerequisite:** `CX-LANG-UTILS` (step 2) must already be deployed — the industry's inbound flow consumes the external SSM parameter `/flows/init/es` (the `init-flow-es-v2` module) as its start module.

```bash
cd agentic-cx-{industry}
source ../.env            # INSTANCE_ALIAS + INSTANCE_ID + ASSISTANT_ID (step 0a)
source .venv/bin/activate
cdk diff                  # verification gate
cdk deploy --all          # or deploy phase by phase (order below)
```

Phase order (enforced by `add_stack_dependency`, ordering only — values cross stacks via SSM, never `Fn::ImportValue`):

| Order | Stack | What it deploys |
|---|---|---|
| 1 | **`CX-{INDUSTRY}-MCP`** | DynamoDB tables + seed data, the Lambda backend, the industry's REST API (API key in Secrets Manager), the **AgentCore MCP gateway** (re-exposes the REST API as MCP tools, with an API-key credential provider + inline OpenAPI target), and the Connect integrations (registers the gateway as an MCP server app + associates the Lambdas the flows consume). |
| 1 | **`CX-{INDUSTRY}-KB`** | KMS key + S3 bucket with the KB articles (es/pt/en), an AppIntegrations DataIntegration, the **EXTERNAL Q in Connect knowledge base** that crawls the bucket, and the assistant association that binds the KB to the AI agents domain. *Independent of MCP — can deploy in parallel.* |
| 2 | **`CX-{INDUSTRY}-CONNECT-SUPPORT`** | The AI agents' **security profiles** (self-service + agent-assist, `Wisdom.View` + `CustomViews.Access` + the deploy-time MCP tool grant), **customer-managed views** (the guided form + the step-by-step guide view), the **guide contact flow** (`GUIDE_FLOW_NAME`), and the **Lex V2 Q-in-Connect passthrough bot** (`{industry}-qconnect-bot-v2`, 3 locales, Nova Sonic v2, TestBotAlias ARN published to SSM). |
| 3 | **`CX-{INDUSTRY}-AGENTS`** | The **orchestration AI prompts** and the **three AI agents** — self-service **voice** + **chat** (KB Retrieve + AgentCore MCP tools + Escalate/Complete; chat adds the guided form) and **agent-assist** (Retrieve + MCP surface). Consumes the MCP tool prefix (Phase 1) and the KB association id (Phase 2). |
| 4 | **`CX-{INDUSTRY}-FLOWS`** | The escalation **handoff view**, the **screen-pop flow** (registers the view as `DefaultAgentUI`), the **flow modules** (`escalate-to-agent`, `set-customer-session-{industry}`), and the **Spanish self-service inbound flow** (creates the Wisdom session, binds the Lex bot + the three agents, drives the guided form, escalates to a human). Resolves the BasicQueue ARN by name at deploy time. |
| 5 | **`CX-{INDUSTRY}-WEBSITE`** | The industry's static site → **private S3 + CloudFront (OAC)**, hosting the Amazon Connect **chat widget** and a demo data viewer at **`/datos`** (a Lambda that renders the Phase 1 DynamoDB tables). Ordered after MCP (ordering only). |

---

## 5. [SCRIPT] Post-deployment: tag the KB content + associate the guide

Run this after `CX-{INDUSTRY}-KB` finishes its first **asynchronous** sync (this cannot be a CloudFormation resource because the crawler creates new, untagged content ids on every sync). From `agentic-cx-{industry}/`, with the venv active, `source ../.env` done (the scripts import `config.py`, which requires all three variables), and your AWS profile/region set in the environment:

```bash
# 1) Tag every content item so the agents' Retrieve filter can find it.
#    the kb-id resolves from SSM automatically; --wait polls until ingestion is ACTIVE.
python knowledge_bases/tag_kb_content.py --wait --expect 21

# 2) Bind the step-by-step guide flow to its KB article(s) (idempotent).
#    Shared script: resolves the flow (GUIDE_FLOW_NAME) and the match text
#    (GUIDE_CONTENT_MATCH) from config.py, and associates every language copy of the article.
python knowledge_bases/associate_guide.py        # add --dry-run to preview
```

> If `--expect 21` does not match your actual ingestion count, adjust it (or drop `--expect`) or `--wait` will time out.

---

## 6. [MANUAL] Post-deployment console steps

These have no native CloudFormation resource and must be done by hand:

1. **Attach the security profile to each AI agent and publish a new version.** In the **Amazon Connect** admin website → **AI agents** (your Q in Connect domain), open each agent, **attach its security profile**, then **Save and Publish a new version**:
   - `{industry}-selfservice-voice-es` and `{industry}-selfservice-chat-es` → the project's **self-service** security profile (`config.AI_AGENT_SECURITY_PROFILE_NAME`)
   - `{industry}-agent-assist-es` → the **agent-assist** profile (`config.AI_AGENT_ASSIST_SECURITY_PROFILE_NAME`)
   - For **agent-assist**, the human agents who use the assistant panel must also carry the same permissions (`Wisdom.View`, `CustomViews.Access`, the MCP tool grant) — tool calls are authorized against the intersection of the AI agent's and the human agent's profiles. (The profile ids are also published to SSM for scripting.)

   > **Mandatory — this is what authorizes the MCP tool calls.** The AgentCore MCP tools are granted through the security profile, and the running agent uses the **published version**. If the profile is not attached (or you edited it but did not publish a new version), MCP tool calls fail at invocation with `Target entity not found` even though the gateway/target and the backend REST API are healthy. After attaching the profile, always **publish a new version** and confirm the flow/binding points at that version.

2. **Take control of the bot from Amazon Connect (toggle Lex Bot Management) — do this _before_ building the locales.** Because the bot is created on the **Amazon Lex** side (via CDK), the Connect instance does not refresh its Lex Bot Management link automatically, so the bot will not be selectable/editable inside Connect flows until you toggle the feature. In the **Amazon Connect** console → your instance → **Flows** → **Amazon Lex Bots** section:

   1. Uncheck **Enable Lex Bot Management in Amazon Connect** → **Save** (disable → save).
   2. Re-check **Enable Lex Bot Management in Amazon Connect** → **Save** (enable → save).

   Connect creates the **service role** and the **service-linked role** for you as part of this toggle, and `{industry}-qconnect-bot-v2` becomes visible to the instance. (You do **not** need to create the Lex service-linked role by hand.)

3. **Build the Lex bot locales** (Amazon Lex V2 console): open `{industry}-qconnect-bot-v2` and build `en_US`, `es_US`, `pt_BR` **if they are not already in BUILD state** (the state is shown next to each locale). They are intentionally not auto-built to keep deployments fast; once built, the TestBotAlias (`TSTALIASID`) serves DRAFT and the inbound flow (already bound via SSM) works. If all three locales already show **Built**, you can skip this step.

   > **Enable the locales on the TestBotAlias too.** After building, make sure each locale (`en_US`/`es_US`/`pt_BR`) is enabled on the **TestBotAlias**. If a locale is not enabled on the alias the flow uses, chat fails at the `ConnectParticipantWithLexBot` step with `The BotAliasId TSTALIASID does not have Language <locale> enabled`. Some apps wire this automatically with a small custom resource in `CX-{INDUSTRY}-CONNECT-SUPPORT`; if yours does not, confirm it in the console (Aliases → TestBotAlias → Languages) or via `aws lexv2-models update-bot-alias`. In every case you still need to **build** all three locales in the Lex console if they are not built already.

---

## 7. [MANUAL] Wire the chat widget into the website

1. In the **Amazon Connect** console, create a **chat communications widget**. When creating it, add your **approved origins** so the widget can load:
   - `http://localhost` (and/or `http://localhost:<port>`) for local development.
   - The CloudFront domain from the site stack's output, e.g. `https://{id}.cloudfront.net` (the `WebsiteDistributionDomainName` / `WebsiteDataViewerPath` output of `CX-{INDUSTRY}-WEBSITE`).

   > The widget will fail silently to load on any origin not in this list. Because the CloudFront domain is unknown until the site stack deploys, you normally create the widget, deploy the site, and then come back to add the real `*.cloudfront.net` origin (a custom domain works too once configured).
2. Open `agentic-cx-{industry}/website/index.html` and **update the Connect widget**: replace the content **between** these two markers with your generated widget snippet, as is — leave the markers in place:

   ```html
   <!--REPLACE WITH CONNECT WIDGET AS IS (BELOW THIS LINE)-->
   [YOUR WIDGET CONTENT GOES HERE]
   <!--END OF CONNECT WIDGET (ABOVE THIS LINE)-->
   ```

   > **Passing the logged-in user's email as a contact attribute.** The site registers `window._connectContactAttrs` as the widget's `contactAttributes` object **once**, and then mutates that same object reference on sign-in/sign-out. Keep that pattern: if you build a new object on every `contactAttributes` call, the widget never sees the post-login email, and the customer lookup cannot personalize the contact.

3. Rebuild and redeploy the site:

```bash
cd agentic-cx-{industry}/website
npm run build
cd ..
cdk deploy CX-{INDUSTRY}-WEBSITE
```

---

## Manual / script steps at a glance

| # | Type | Step |
|---|---|---|
| 0 | manual | `cdk bootstrap aws://<account-id>/<region>` (per account/region) |
| 0 | manual | `python3 -m venv .venv` in each CDK app (`general-localization`, `agentic-cx-{industry}`) |
| 0a | manual | `cp .env.example .env` at the repo root, fill it in, and `source ../.env` in every shell before `cdk` or the scripts |
| 1 | manual | Create the Connect instance + the Q in Connect assistant; set `INSTANCE_ALIAS` / `INSTANCE_ID` / `ASSISTANT_ID` in `.env` |
| 2 | manual | Set the localized utility agents as the domain defaults (Answer Recommendation / Manual Search / Note Taking) |
| 3 | manual | `npm install && npm run build` for the site before each app's deployment |
| 5 | script | `tag_kb_content.py --wait` (the KB id auto-resolves from SSM) |
| 5 | script | `associate_guide.py` — single shared script; associates the guide belonging to each industry (resolved from `GUIDE_FLOW_NAME` / `GUIDE_CONTENT_MATCH` in `config.py`) |
| 6 | manual | Attach the Phase 3 security profiles to the three AI agents (authorizes the MCP tools), then **publish a new version** — without this, tool calls fail with `Target entity not found` |
| 6 | manual | Take control of the bot in Connect: Flows → toggle Lex Bot Management off+save, on+save (creates the roles) — do this **before** building the locales |
| 6 | manual | Build the Lex bot's `en_US` / `es_US` / `pt_BR` locales (if not already **Built**) and confirm they are enabled on the TestBotAlias |
| 7 | manual | Create the chat widget (add `http://localhost` + the `https://{id}.cloudfront.net` output as **approved origins**), paste it between the widget markers in `website/index.html`, rebuild + redeploy the site |

> Repeat steps **3–7** for each industry (`telco`, `banco`, `airline`) you want to deploy, substituting `{industry}` / `{INDUSTRY}`.

> Once deployed, each app carries a demo script with the exact questions to use: `agentic-cx-{industry}/DEMO-WALKTHROUGH-en.md` (Spanish: `DEMO-WALKTHROUGH.md`).

> The full per-stack detail, the SSM contract between stacks, and the configuration reference live in each app's `README.md` (`agentic-cx-{industry}/README.md`, Spanish only).
