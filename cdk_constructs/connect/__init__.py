"""cdk_constructs.connect — shared, industry-agnostic Amazon Connect constructs.

These wrap ``aws_connect`` / ``aws_wisdom`` / ``aws_lex`` / custom resources and
take everything as explicit parameters (no ambient ``import config``): instance
ARN, resource name, the path to the authored JSON, and any ``replacements``. The
authored flow/view JSONs and any business-specific code stay in each industry
app; only the construct classes live here.
"""

from cdk_constructs.connect.ai_agents import (
    AgentSurface,
    AgentToolset,
    OrchestrationAIAgent,
    build_tools,
    rtc_tool_dict,
)
from cdk_constructs.connect.ai_prompts import OrchestrationPrompt
from cdk_constructs.connect.basic_queue_lookup_cr import BasicQueueLookup
from cdk_constructs.connect.flows import ContactFlow, ContactFlowModule
from cdk_constructs.connect.lex_bot import QInConnectLexBot
from cdk_constructs.connect.security_profile import (
    DEFAULT_AI_AGENT_PERMISSIONS,
    AiAgentSecurityProfile,
)
from cdk_constructs.connect.views import CustomerManagedView

__all__ = [
    "AgentSurface",
    "AgentToolset",
    "AiAgentSecurityProfile",
    "BasicQueueLookup",
    "ContactFlow",
    "ContactFlowModule",
    "CustomerManagedView",
    "DEFAULT_AI_AGENT_PERMISSIONS",
    "OrchestrationAIAgent",
    "OrchestrationPrompt",
    "QInConnectLexBot",
    "build_tools",
    "rtc_tool_dict",
]
