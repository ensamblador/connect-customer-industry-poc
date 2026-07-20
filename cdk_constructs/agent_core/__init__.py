"""cdk_constructs.agent_core — shared Bedrock AgentCore constructs.

``AgentCoreGateway`` (MCP gateway with inbound JWT + inline-OpenAPI target and
the single-deploy audience self-patch) and ``ApiKeyCredentialProvider`` (the
AgentCore API-key credential provider custom resource). Both are
industry-agnostic — the gateway name, discovery URL, and the backing secret are
passed in by each app's MCP stack.
"""

from cdk_constructs.agent_core.agent_core_gateway import AgentCoreGateway
from cdk_constructs.agent_core.api_key_credential_provider import ApiKeyCredentialProvider

__all__ = ["AgentCoreGateway", "ApiKeyCredentialProvider"]
