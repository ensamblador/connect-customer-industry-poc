#!/usr/bin/env python3
"""CDK app entry point for the agentic-cx-bank sample.

Phased, decoupled stacks that pass values to each other only through SSM
Parameter Store (shared/ssm_names.py) — no CloudFormation exports, no nested
stacks. Deploy order is enforced with stack.add_dependency (ordering only; it
emits no Fn::ImportValue).

Phases (added incrementally):
    1. McpStack            — data + compute + REST API + AgentCore MCP gateway
    2. KnowledgeBaseStack  — EXTERNAL Q in Connect knowledge base (Spanish)
    3. ConnectSupportStack — security profiles + views + guide flow
    4. AiAgentsStack       — Orchestration AI prompts + agents
    5. ContactFlowsStack   — flow modules + contact flows
    6. WebsiteStack        — static "Latam Banco" site (S3 + CloudFront, independent)
"""

import aws_cdk as cdk

import config
from agentic_cx_bank.mcp_stack import McpStack
from agentic_cx_bank.knowledge_base_stack import KnowledgeBaseStack
from agentic_cx_bank.connect_support_stack import ConnectSupportStack
from agentic_cx_bank.ai_agents_stack import AiAgentsStack
from agentic_cx_bank.contact_flows_stack import ContactFlowsStack
from agentic_cx_bank.website_stack import WebsiteStack

app = cdk.App()
# Phase 1 — MCP / AgentCore foundation.
mcp = McpStack(app, "CX-BANCO-MCP")

# Phase 2 — Q in Connect knowledge base. Independent of Phase 1: it consumes no
# SSM value from MCP, so there is no dependency edge — it can deploy in any
# order / in parallel.
kb = KnowledgeBaseStack(app, "CX-BANCO-KB")

# Phase 3 — Connect supporting resources (security profiles + views + guide
# flow/association). Consumes the gateway id from Phase 1 (security-profile
# MCP grant namespace) and the KB id from Phase 2 (content association), so
# it depends on BOTH. Edges are ordering-only (no Fn::ImportValue).
support = ConnectSupportStack(app, "CX-BANCO-CONNECT-SUPPORT")
support.add_dependency(mcp)
support.add_dependency(kb)

# Phase 4 — AI prompts + the agents. The prompts only need the Q in Connect
# domain id (config); the agents consume MCP_TOOL_PREFIX (Phase 1) and
# KB_ASSOC_ID (Phase 2). Agents are created as drafts only; assigning each
# agent's security profile is a MANUAL post-deploy step (Phase 3 publishes the
# profile ids to SSM for it), so this stack no longer depends on `support`.
agents = AiAgentsStack(app, "CX-BANCO-AGENTS")
agents.add_dependency(kb)
agents.add_dependency(mcp)

# Phase 5 — contact flow modules + contact flows. Consumes the ai_session
# Lambda ARN (Phase 1), the view ARN + Lex bot alias ARN (Phase 3), and the
# agent ARNs (Phase 4). Resolves every *_PLACEHOLDER marker in the flow JSON
# at synth. The BasicQueue is left literal (manual re-select).
flows = ContactFlowsStack(app, "CX-BANCO-FLOWS")
flows.add_dependency(mcp)
flows.add_dependency(support)
flows.add_dependency(agents)

# Phase 6 — static "Latam Banco" website (S3 private + CloudFront OAC). Hosts
# the Amazon Connect chat widget and passes the logged-in email as a contact
# attribute. Its demo data-viewer Lambda reads the Phase 1 DynamoDB tables at
# runtime, so it is ordered after MCP — an ordering-only edge: the table ARNs
# are reconstructed from config names, with no Fn::ImportValue. Build the site
# first (cd website && npm install && npm run build); gated by config.BUILD_WEBSITE.
web = WebsiteStack(app, "CX-BANCO-WEBSITE")
web.add_dependency(flows)
web.add_dependency(mcp)

app.synth()
