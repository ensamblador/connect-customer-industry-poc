"""shared/ssm_names.py — the cross-stack SSM contract for agentic-cx-telco.

Every parameter name the phased stacks read/write lives here ONCE. Producer and
consumer stacks both import these constants, so a name can never drift between
the write side and the read side.

Names are plain ``String`` params under the ``/agentic-cx-telco/<phase>/<key>``
namespace (no secrets — the REST API key stays in Secrets Manager and never
crosses a stack boundary).

Cross-stack values travel ONLY through these parameters — no CloudFormation
exports / ``Fn::ImportValue`` and no nested stacks. Consumers resolve at DEPLOY
time via ``value_for_string_parameter`` (an ``AWS::SSM::Parameter::Value<String>``
template parameter), and deploy order is enforced separately with
``stack.add_dependency`` in ``app.py``.

This registry holds ONLY the values that genuinely cross a stack boundary.
Everything else a phase produces (REST API id/url, gateway url, table names,
agent qualified ids, the eSIM view/flow ARNs that are consumed inside their own
stack, ...) stays a CfnOutput for humans/ops and is intentionally NOT on the bus.
"""

from __future__ import annotations

from aws_cdk import aws_ssm as ssm
from constructs import Construct

NS = "/agentic-cx-telco"

# --- Phase 1: MCP / AgentCore foundation (mcp_stack) ----------------------
# Bare gateway id — consumed by Phase 3 as the security-profile MCP application
# namespace (and is the value Connect uses as the inbound JWT audience).
GATEWAY_ID = f"{NS}/agentcore/gateway-id"
# Full agent toolId prefix "gateway_<id>__<target>___" — consumed by Phase 4
# agents (tool ids are this prefix + each operationId).
MCP_TOOL_PREFIX = f"{NS}/agentcore/mcp-tool-prefix"
# Lambda ARNs the Phase 5 contact flows invoke directly (Invoke-Lambda blocks /
# module markers). accounts + lines back the API/MCP tools only, so they are
# NOT published.
LAMBDA_PLANS_ARN = f"{NS}/agentcore/lambda/plans-arn"
LAMBDA_AI_SESSION_ARN = f"{NS}/agentcore/lambda/ai-session-arn"

# --- Phase 2: Knowledge base (knowledge_base_stack) -----------------------
KB_ID = f"{NS}/kb/knowledge-base-id"  # consumed by Phase 3 (eSIM content association)
KB_ASSOC_ID = f"{NS}/kb/assistant-association-id"  # consumed by Phase 4 (Retrieve binding)

# --- Phase 3: Connect support (connect_support_stack) ---------------------
SP_SELFSERVICE_ID = f"{NS}/connect/security-profile-selfservice-id"  # manual agent assignment
SP_ASSIST_ID = f"{NS}/connect/security-profile-assist-id"  # manual agent assignment
VIEW_NEWLINE_ARN = f"{NS}/connect/view-newline-qualified-arn"  # -> Phase 5 (ShowView)
LEX_BOT_ALIAS_ARN = f"{NS}/connect/lex-bot-alias-arn"  # -> Phase 5 (inbound flow GetCustomerInput)

# --- Phase 4: AI agents (ai_agents_stack) ---------------------------------
AGENT_VOICE_ARN = f"{NS}/agents/voice-arn"  # -> Phase 5 (inbound flow voice binding)
AGENT_CHAT_ARN = f"{NS}/agents/chat-arn"  # -> Phase 5 (chat binding)
AGENT_ASSIST_ARN = f"{NS}/agents/assist-arn"  # -> Phase 5 (agent-assist binding)

# --- External: published by CX-LANG-UTILS (general-localization app) -------
# The shared init-flow-es contact-flow MODULE ARN (set-logging + recording +
# customer-queue event hook). Created by a SEPARATE app on the SAME instance
# and consumed by the Phase 5 inbound flow as its StartAction module. This name
# lives OUTSIDE the /agentic-cx-telco namespace because CX-LANG-UTILS owns it;
# CX-LANG-UTILS must be deployed first so the parameter exists at deploy time.
INIT_FLOW_MODULE_ARN = "/flows/init/es"


def publish(
    scope: Construct, logical_id: str, name: str, value: str
) -> ssm.StringParameter:
    """Producer side: write a plain ``String`` parameter at an EXPLICIT name.

    Values are ids / ARNs / URLs (never secrets), so the parameter is a plain
    ``String`` on the STANDARD tier. No CloudFormation Output/Export is created.
    """
    return ssm.StringParameter(
        scope,
        logical_id,
        parameter_name=name,
        string_value=value,
        tier=ssm.ParameterTier.STANDARD,
    )


def consume(scope: Construct, name: str) -> str:
    """Consumer side: resolve a parameter at DEPLOY time.

    Emits an ``AWS::SSM::Parameter::Value<String>`` template parameter — no
    synth-time SDK call, no ``cdk.context.json`` cache, and NO cross-stack
    export. The returned token resolves to the current SSM value at deploy time.
    """
    return ssm.StringParameter.value_for_string_parameter(scope, name)
