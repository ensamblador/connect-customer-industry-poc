"""
config.py — flat configuration for the CDK project, GROUPED BY STACK.

Module-level constants only (no classes). Import the values you need directly,
e.g. `from config import INSTANCE_ALIAS, OIDC_DISCOVERY_URL`.

No secrets live here. AWS credentials resolve from your local AWS profile / SSO
at deploy time; the account/region come from the CDK environment.

Layout: constants are ordered by the deploy phase that FIRST consumes them
(Phase 1 MCP → Phase 6 Website), so each value sits next to the stack that
needs it. A value consumed by several stacks is declared once, under the
EARLIEST phase that uses it, with a note listing the other consumers. The
deploy order (see app.py):

    Phase 1  CX-BANCO-MCP             McpStack
    Phase 2  CX-BANCO-KB              KnowledgeBaseStack
    Phase 3  CX-BANCO-CONNECT-SUPPORT ConnectSupportStack
    Phase 4  CX-BANCO-AGENTS          AiAgentsStack
    Phase 5  CX-BANCO-FLOWS           ContactFlowsStack
    Phase 6  CX-BANCO-WEBSITE         WebsiteStack

Two trailing sections hold values that are NOT consumed by a stack: those read
by post-deploy operational scripts, and those not referenced anywhere today.

This project re-themes the shared reference architecture for retail banking: the
flat, phase-grouped structure and every constant name are preserved; only the
domain values change. Every resource name is industry-prefixed so it never
collides with a sibling project's resources on the shared Connect instance.
"""

import os

# ========================================================================== #
# SHARED — Amazon Connect identity (consumed from Phase 1 onward by every stack)
# ========================================================================== #
# Fill these in with your real Connect instance values. Placeholders let the
# stacks synthesize without a live instance (HAS_REAL_INSTANCE gates the
# instance-bound resources). These three identity values are the single source
# of truth referenced by every consumer (they intentionally match the shared
# instance across the sibling industry projects).
INSTANCE_ALIAS = "chat-demos-latam"
INSTANCE_ID = "30b0e238-b3bd-4f61-9f04-c0b24e4a2f74"

# The Connect Q in Connect assistant id (a.k.a. the "AI agents domain" id — the
# same resource). Single source of truth for every assistant reference
# (consumed by Phase 1 ai-session env, Phase 2 KB association, Phase 3 Lex bot,
# Phase 4 prompts/agents/logging, Phase 5 flow ASSISTANT_ARN).

ASSISTANT_ID = "e1de1c2a-08ea-49e9-9dae-2ad3c80e78fd"
# ========================================================================== #
# PHASE 1 — CX-BANCO-MCP (McpStack)
# data + compute + REST API + AgentCore MCP gateway + Connect MCP/Lambda integ.
# ========================================================================== #
# REST API naming.
API_NAME = "banco-api"
API_STAGE_NAME = "prod"
# AgentCore MCP gateway name (also used for the api-key credential provider and
# the Connect MCP application name).
GATEWAY_NAME = "banco-mcp-server"

# DynamoDB tables backing the REST API / MCP tools.
ACCOUNTS_TABLE_NAME = "banco-accounts"
PLANS_TABLE_NAME = "banco-products"
LINES_TABLE_NAME = "banco-cards"

# MCP gateway target name. Phase 1 builds the agent toolId prefix
# "gateway_<id>__<target>___" from it; Phase 3 reuses it to build the
# security-profile MCP tool grant ("<target>___<op>"). The 9 operationIds
# themselves live in the Phase 3 section (AI_AGENT_MCP_OPERATIONS).
AI_AGENT_MCP_TARGET = "banco-rest-api-oas-target"

# --- Derived: Connect OIDC discovery URL + real-instance flag -------------
# Identity provider for the AgentCore gateway's inbound JWT authorizer (Phase 1
# gateway). The gateway is created with a placeholder audience and an
# UpdateGateway custom resource patches allowedAudience to the gateway's own id
# in a single deploy (Connect issues the inbound JWT with aud = <gateway id>),
# so no audience value is configured here.
OIDC_DISCOVERY_URL = (
    f"https://{INSTANCE_ALIAS}.my.connect.aws/.well-known/openid-configuration"
)
# True only when a real instance alias has been set. Gates every instance-bound
# resource (consumed by Phases 1, 3, 4, 5).
HAS_REAL_INSTANCE = INSTANCE_ALIAS != "replace-with-connect-instance-alias"

# ========================================================================== #
# PHASE 2 — CX-BANCO-KB (KnowledgeBaseStack)
# EXTERNAL S3-backed Q in Connect knowledge base (multi-language) + assistant
# association. (The assistant it binds to is the shared ASSISTANT_ID above.)
# ========================================================================== #
KB_NAME = "banco-kb"
# Local plain-text (.txt) entries root (relative to the app root); one subfolder per language
# (es/, pt/, en/). A BucketDeployment uploads the whole tree to the KB bucket
# under KB_BUCKET_PREFIX so one KB serves every language.
KB_ENTRIES_DIR = "knowledge_bases/bank/entries"
# Logical S3 path prefix for the uploaded entries (organizational only — the
# DataIntegration SourceURI is the whole bucket): bank/es/..., bank/pt/..., etc.
KB_BUCKET_PREFIX = "bank"

# ========================================================================== #
# PHASE 3 — CX-BANCO-CONNECT-SUPPORT (ConnectSupportStack)
# AI-agent security profiles + customer-managed views + activate-card guide flow + Lex bot.
# ========================================================================== #
# --- AI-agent security profiles ---
# Least-privilege Connect security profile assigned to the AI agents. Permissions
# mirror the agents' tools (admin guide: "Assigning security profile permissions
# to AI agents"):
#   * "Wisdom.View"        — KB Retrieve tool + "Connect AI agents - View"
#                            (real-time recommendations in the agent app).
#   * "CustomViews.Access" — lets the workspace launch the step-by-step GUIDES
#                            surfaced from a recommendation (the activate-card guide).
AI_AGENT_SECURITY_PROFILE_NAME = "banco-selfservice-ai-agent"
AI_AGENT_SECURITY_PROFILE_PERMISSIONS = ["Wisdom.View", "CustomViews.Access"]
# Dedicated profile for the agent-assistance AI agent. NOTE: in agent-assistance,
# tool calls authorize against the INTERSECTION of the AI agent's profile AND the
# human agent's profile, so human agents using the assistant panel must ALSO
# carry these permissions or the tools fail in their session.
AI_AGENT_ASSIST_SECURITY_PROFILE_NAME = "banco-agent-assist-iac"

# MCP tool access is granted via the security profile's `applications` block
# (Type=MCP), not flat permissions. The namespace is the bare gateway id (read
# from SSM GATEWAY_ID at deploy time); the per-tool ids are "<target>___<op>"
# (AI_AGENT_MCP_TARGET from Phase 1 + each operationId below). Max 10 tools per
# application. Toggle the grant off to deploy the profiles with Wisdom.View +
# CustomViews.Access only while confirming the exact tool-id strings in the
# console security-profile editor.
BUILD_AI_AGENT_MCP_GRANT = True
# The 9 gateway operations (OpenAPI operationIds) exposed as MCP tools.
AI_AGENT_MCP_OPERATIONS = [
    "getAccountByPhone",
    "getAccountByEmail",
    "getAccount",
    "getAccountBalance",
    "listProducts",
    "getProduct",
    "requestCard",
    "listCustomerCards",
    "getCard",
]

# --- Customer-managed views ---
# The card-request guided form (AWS::Connect::View), rendered in the chat window by a
# "Show view" (ShowView) block; authored payload in views/<name>/view-content.json.
NEWLINE_VIEW_NAME = "BancoCardRequestForm"
NEWLINE_VIEW_CONTENT = "views/banco-card-request-form/view-content.json"

# --- Activate-card step-by-step guide ---
# Agent-facing guide: a customer-managed view renders the steps, driven by a
# guide contact flow that chains ShowView blocks. The view + guide flow are built
# here; the AMAZON_CONNECT_GUIDE content association that binds the flow to the
# KB content is a post-deploy step (see GUIDE_CONTENT_MATCH in the
# Scripts section). GUIDE_FLOW_NAME names the flow here AND lets the script
# resolve its ARN by name.
GUIDE_VIEW_NAME = "BancoCardActivationGuide"
GUIDE_VIEW_CONTENT = "views/banco-card-activation-guide/view-content.json"
FLOW_GUIDE = "flows/banco-card-activation-guide-es/flow.json"
# Flow name == the label shown on the step-by-step GUIDE button in the agent
# panel (Q in Connect renders the guide button using the flow's name). Also how
# associate_guide.py resolves the flow ARN. AWS::Connect::ContactFlow
# updates Name in place (no replacement), so renaming + redeploy relabels the
# button without breaking the existing content association.
GUIDE_FLOW_NAME = "Activar tarjeta"

# --- Lex V2 Q-in-Connect passthrough bot ---
# A Nova Sonic v2 bot whose single AMAZON.QInConnectIntent delegates to the
# ASSISTANT_ID assistant (3 locales en_US/es_US/pt_BR). The stack publishes the
# bot's alias ARN to SSM (LEX_BOT_ALIAS_ARN); the Phase 5 inbound flow consumes it.
LEX_BOT_NAME = "banco-qconnect-bot-v2"

# ========================================================================== #
# PHASE 4 — CX-BANCO-AGENTS (AiAgentsStack)
# Orchestration AI prompts + the three AI agents (voice / chat / agent-assist).
# ========================================================================== #
# Active AI agent locale.
AI_AGENT_LOCALE = "es_US"

# Prompt YAML paths (relative to the app root) + the orchestration model each
# prompt runs (kept as authored in the live domain, NOT forced to one model).
# Authoring path is native AWS::Wisdom::AIAgent (CfnAIAgent); tool input schemas
# must not carry `maxLength` (the provider stringifies it -> invalid JSON Schema
# -> breaks orchestration; see cdk_constructs/connect/ai_agents.py). The `<sources>` citation
# behavior is enforced by the system Retrieve tool, not these bodies.
AI_AGENT_VOICE_PROMPT = "connect_ai_agents/bank-selfservice-voice/prompts/banco-selfservice-orchestration-voice.yaml"
AI_AGENT_VOICE_MODEL = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
AI_AGENT_CHAT_PROMPT = "connect_ai_agents/bank-selfservice-chat/prompts/banco-selfservice-orchestration-chat.yaml"
AI_AGENT_CHAT_MODEL = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
AI_AGENT_ASSIST_PROMPT = "connect_ai_agents/bank-agent-assist-es/prompts/banco-agent-assist-orchestration-es.yaml"
AI_AGENT_ASSIST_MODEL = "global.anthropic.claude-sonnet-4-6"

# Per-language content segmentation for the agents' Retrieve tool. The filter
# ANDs industry=bank with this language so a Spanish agent never retrieves the
# pt/en copies. KB_LANGUAGE_TAG_KEY must match tag_kb_content.py's --language-key;
# set AI_AGENT_CONTENT_LANGUAGE to "" to retrieve across all languages.
KB_LANGUAGE_TAG_KEY = "language"
AI_AGENT_CONTENT_LANGUAGE = "es"

# NOTE: AI-agent CloudWatch logging (EVENT_LOGS vended-log delivery) is NOT
# configured here. ASSISTANT_ID is shared across every industry project on
# this account, and CloudWatch Logs allows only one EVENT_LOGS delivery source
# per resource, so that logging is provisioned ONCE in the shared
# `general-localization` (CX-LANG-UTILS) app instead (see
# general-localization/connect/ai_agent_logging.py and its config.py
# ENABLE_AGENT_LOGS / AGENT_LOGS_GROUP_NAME constants).

# ========================================================================== #
# PHASE 5 — CX-BANCO-FLOWS (ContactFlowsStack)
# Contact flows + modules. Flow JSON lives under flows/<name>/flow.json; cross-
# stack values resolve from *_PLACEHOLDER markers at synth. NOTE: flow names are
# unique per instance — a CDK flow named like a live hand-built flow collides.
# ========================================================================== #
FLOW_SCREENPOP = "flows/banco-agent-screenpop-es/flow.json"
FLOW_ESCALATE_MODULE = "flows/banco-escalate-to-agent/flow.json"
FLOW_INBOUND = "flows/banco-selfservice-es-inbound/flow.json"
# Module that classifies the contact endpoint, looks the customer up via the
# ai-session-banco Lambda, and writes the record into the Q in Connect session.
FLOW_SET_CUSTOMER_SESSION = "flows/set-customer-session-banco/flow.json"

# The BasicQueue the escalate module + inbound flow transfer to. Queue ids are
# unique PER INSTANCE, so by default the flows stack RESOLVES the queue at DEPLOY
# time by NAME (BASIC_QUEUE_NAME) via a connect:ListQueues custom resource. Set
# BASIC_QUEUE_ID to pin a specific queue id and skip the lookup.
BASIC_QUEUE_NAME = "BasicQueue"
BASIC_QUEUE_ID = ""

# Agent screen-pop handoff view (AWS::Connect::View), rendered by the screen-pop
# flow on agent accept (referenced via HANDOFF_VIEW_ARN_PLACEHOLDER).
ESCALATION_HANDOFF_VIEW_NAME = "BancoEscalationHandoff"
ESCALATION_HANDOFF_VIEW_CONTENT = "views/banco-escalation-handoff/view-content.json"

# ========================================================================== #
# PHASE 6 — CX-BANCO-WEBSITE (WebsiteStack)
# Static "Latam Banco" site: Vite build (website/dist) → private S3 + CloudFront
# OAC. Build first (cd website && npm install && npm run build). Gated by
# BUILD_WEBSITE so the stack synthesizes empty before the site is built.
# ========================================================================== #
BUILD_WEBSITE = True
# Vite build output directory deployed to S3.
WEBSITE_ASSETS_PATH = "website/dist"
# S3 destination prefix (empty = bucket root).
WEBSITE_DESTINATION_KEY_PREFIX = ""
# CloudFront settings.
WEBSITE_DEFAULT_ROOT_OBJECT = "index.html"
WEBSITE_INVALIDATION_PATHS = ["/index.html"]
WEBSITE_PRICE_CLASS = "PRICE_CLASS_100"
WEBSITE_HTTP_VERSION = "HTTP2"
WEBSITE_VIEWER_PROTOCOL_POLICY = "REDIRECT_TO_HTTPS"
# NOTE: the SPA-style error mapping (403/404 → index.html) is a fixed standard
# baked into the website hosting construct (cdk_constructs/webhosting/webhosting_construct.py),
# not a config knob.

# ========================================================================== #
# POST-DEPLOY SCRIPTS (not consumed by any stack)
# ========================================================================== #
# knowledge_bases/associate_guide.py finds the activate-card KB
# content by this title substring and creates the AMAZON_CONNECT_GUIDE
# association to the guide flow (resolved by GUIDE_FLOW_NAME). Run it after
# the KB syncs — the content ids are post-ingestion values, so none are
# hard-coded here.
GUIDE_CONTENT_MATCH = "activar-tarjeta"
# (The KB content tagging script, knowledge_bases/tag_kb_content.py, reads its
# tags from knowledge_bases/bank/manifest.json, not from this file.)

# ========================================================================== #
# NOT CURRENTLY CONSUMED (kept for reference; no stack/script reads these today)
# ========================================================================== #
# General project name — no current consumer.
PROJECT_NAME = "banco-cx"
# DynamoDB GSI names — the DataTables construct defines its own index-name
# constants, so these config copies are unreferenced.
PHONE_INDEX_NAME = "phoneNumber-index"
CUSTOMER_INDEX_NAME = "customerId-index"
# Base KB segmentation tags — tag_kb_content.py reads tags from manifest.json,
# not here, so this is unreferenced.
KB_CONTENT_TAGS = {"industry": "bank"}
# Agent build toggles — the AiAgentsStack gates on HAS_REAL_INSTANCE, not these.
BUILD_AI_AGENTS = True
BUILD_AGENT_ASSIST = True

