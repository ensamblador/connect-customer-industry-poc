"""
agentic_cx_bank/mcp_stack.py — Phase 1: the MCP / AgentCore foundation.

This is the first phased stack of the agentic-cx-bank sample. It composes the
banking self-service backend and exposes it to Amazon Connect AI agents as an
MCP server, then publishes the ids/ARNs/URLs the downstream phases need onto the
SSM "bus" (shared/ssm_names.py). Nothing here imports another phase or emits a
CloudFormation export.

Layers (data -> compute -> API -> MCP -> Connect integration), reusing the
per-resource-type constructs verbatim:

    Tables                 databases/databases.py      (L2 dynamodb.Table + seed CR)
    Lambdas                lambdas/project_lambdas.py   (L2 lambda.Function)
    BancoApi               apis/banco_api.py            (L2 apigateway.RestApi + key)
    AgentCoreGateway       cdk_constructs/agent_core/   (L1 CfnGateway/Target)
    ApiKeyCredentialProvider  cdk_constructs/agent_core/ (AgentCore credential provider)
    McpServerIntegration   cdk_constructs/connect/      (AppIntegrations MCP_SERVER)
    LambdaConnectIntegration  cdk_constructs/connect/    (L1 CfnIntegrationAssociation)

Construct choices: standard resources use L1/L2 constructs (DynamoDB, Lambda,
API Gateway, Secrets Manager are L2; the AgentCore gateway + target are the L1
``aws_bedrockagentcore`` CfnGateway / CfnGatewayTarget). The remaining custom
resources are unavoidable — there is no native CFN resource for AgentCore
seed/credential providers, the AppIntegrations MCP_SERVER application, or the
single-deploy gateway-audience patch — and they are isolated inside their own
constructs.

Published SSM parameters (only values that cross a stack boundary):
    GATEWAY_ID (bare id -> Phase 3 profile namespace),
    MCP_TOOL_PREFIX (gateway_<id>__<target>___ -> Phase 4 agents),
    products + ai_session Lambda ARNs (-> Phase 5 flows).
Other ids/urls are surfaced as CfnOutputs only, not on the SSM bus.
"""

from __future__ import annotations

import os

from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_iam as iam
from constructs import Construct

import config
from cdk_constructs.agent_core import AgentCoreGateway, ApiKeyCredentialProvider
from cdk_constructs.apis import openapi_spec
from cdk_constructs.connect import LambdaConnectIntegration, McpServerIntegration
from apis.banco_api import SECRET_API_KEY_JSON_KEY, BancoApi
from databases.databases import Tables
from lambdas.project_lambdas import Lambdas
from shared import ssm_names

# Project root (parent of the app package) — where apis/openapi/openapi.yaml lives.
_APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class McpStack(Stack):
    """Phase 1 — data + compute + REST API + AgentCore MCP gateway + Connect wiring."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.create_resources()
        self.set_up_env_vars()
        self.set_up_permissions()
        self.publish()
        self.create_outputs()

    # ------------------------------------------------------------------ #
    def create_resources(self) -> None:
        # 1. Data layer — all tables (+ sample data loaded via custom resource).
        self.tables = Tables(
            self,
            "Tables",
            accounts_table_name=config.ACCOUNTS_TABLE_NAME,
            products_table_name=config.PLANS_TABLE_NAME,
            cards_table_name=config.LINES_TABLE_NAME,
        )

        # 2. Compute layer — all functions.
        self.lambdas = Lambdas(self, "Lambdas")

        # 3. REST API layer. The API always enforces an API key so the
        # AgentCore API-key credential provider can authenticate.
        self.api = BancoApi(
            self,
            "Api",
            api_name=config.API_NAME,
            stage_name=config.API_STAGE_NAME,
            accounts_fn=self.lambdas.accounts,
            products_fn=self.lambdas.products,
            cards_fn=self.lambdas.cards,
            require_api_key=True,
        )

        # 4. AgentCore MCP gateway fronting the REST API. The gateway is created
        #    with a placeholder audience, then an UpdateGateway custom resource
        #    sets allowedAudience to the gateway's own id in a single deploy
        #    (Connect issues the inbound JWT with aud = <gateway id>).
        self.gateway = AgentCoreGateway(
            self,
            "McpGateway",
            name=config.GATEWAY_NAME,
            discovery_url=config.OIDC_DISCOVERY_URL,
            description="Banking self-service MCP server (accounts, products, cards).",
        )

        # Inline OpenAPI target: the rich authored apis/openapi/openapi.yaml is
        # rendered with the real deployed URL and embedded inline (tool names,
        # descriptions, and IO schemas come from the spec). OpenAPI targets
        # need an explicit credential provider — wire an AgentCore API Key
        # credential provider seeded from the same secret the API Gateway key
        # uses.
        self.api_key_provider = ApiKeyCredentialProvider(
            self,
            "ApiKeyProvider",
            provider_name=f"{config.GATEWAY_NAME}-apikey",
            secret=self.api.api_key_secret,
            secret_json_key=SECRET_API_KEY_JSON_KEY,
        )
        self.openapi_target = self.gateway.add_openapi_inline_target(
            "banco-rest-api-oas",
            spec_json_template=openapi_spec.render_spec_json(
                spec_path=os.path.join(_APP_ROOT, "apis", "openapi", "openapi.yaml"),
                server_description="Deployed banking self-service API Gateway endpoint",
            ),
            rest_api_id=self.api.rest_api_id,
            stage=self.api.stage_name,
            api_key_provider_arn=self.api_key_provider.credential_provider_arn,
            api_key_header_name="x-api-key",
            description="Banking REST API (rich inline OpenAPI) as MCP tools.",
        )

        # 5. Register the gateway as an MCP server integration on the Connect
        # instance (AppIntegrations MCP_SERVER application + APPLICATION
        # association) whenever a real instance is configured. The instance's
        # Discovery URL must be the gateway's.
        if config.HAS_REAL_INSTANCE:
            self.mcp_integration = McpServerIntegration(
                self,
                "McpIntegration",
                instance_id=config.INSTANCE_ID,
                gateway_id=self.gateway.gateway_id,
                gateway_mcp_url=self.gateway.gateway_url,
                # Name the AppIntegrations application after the gateway id (a
                # readable prefix + unique suffix, e.g. banco-mcp-server-<id>)
                # rather than the fixed GATEWAY_NAME. AppIntegrations app names
                # are unique per account/region and CreateApplication fails with
                # "Application name ... already in use" if a stale app from a
                # replaced/deleted gateway still holds the fixed name (and such
                # orphans can't be deleted while a leaked application-association
                # lingers). A gateway-id-based name never collides with a prior
                # gateway's app, so the integration self-heals across rebuilds.
                application_name=self.gateway.gateway_id,
                description="Banking self-service MCP server for Connect AI agent tools.",
            )

        # 5b. Associate the products + ai_session Lambdas with the Connect
        # instance (IntegrationType: LAMBDA_FUNCTION) so contact-flow "Invoke
        # Lambda" blocks (Phase 5) can call them; the association also adds the
        # resource-based policy that lets the Connect service principal invoke.
        if config.HAS_REAL_INSTANCE:
            instance_arn = (
                f"arn:aws:connect:{self.region}:{self.account}:instance/{config.INSTANCE_ID}"
            )
            self.products_lambda_integration = LambdaConnectIntegration(
                self,
                "ProductsLambdaIntegration",
                instance_arn=instance_arn,
                function=self.lambdas.products,
            )
            self.ai_session_lambda_integration = LambdaConnectIntegration(
                self,
                "AiSessionLambdaIntegration",
                instance_arn=instance_arn,
                function=self.lambdas.ai_session,
            )

    # ------------------------------------------------------------------ #
    def set_up_env_vars(self) -> None:
        # accounts: profile/balance by id, plus lookup by phone/email via GSIs.
        self.lambdas.accounts.add_environment(
            "ACCOUNTS_TABLE", self.tables.accounts.table_name
        )
        self.lambdas.accounts.add_environment(
            "ACCOUNTS_PHONE_INDEX", self.tables.PHONE_INDEX_NAME
        )
        self.lambdas.accounts.add_environment(
            "ACCOUNTS_EMAIL_INDEX", self.tables.EMAIL_INDEX_NAME
        )
        # products: catalog.
        self.lambdas.products.add_environment(
            "PRODUCTS_TABLE", self.tables.products.table_name
        )
        # cards: request/list/get, list-by-customer via GSI.
        self.lambdas.cards.add_environment("CARDS_TABLE", self.tables.cards.table_name)
        self.lambdas.cards.add_environment(
            "CARDS_CUSTOMER_INDEX", self.tables.CUSTOMER_INDEX_NAME
        )
        # ai_session: customer lookup by phone/email + Wisdom session write.
        self.lambdas.ai_session.add_environment(
            "ACCOUNTS_TABLE", self.tables.accounts.table_name
        )
        self.lambdas.ai_session.add_environment(
            "ACCOUNTS_PHONE_INDEX", self.tables.PHONE_INDEX_NAME
        )
        self.lambdas.ai_session.add_environment(
            "ACCOUNTS_EMAIL_INDEX", self.tables.EMAIL_INDEX_NAME
        )
        self.lambdas.ai_session.add_environment("AI_ASSISTANT_ID", config.ASSISTANT_ID)
        self.lambdas.ai_session.add_environment(
            "CONNECT_INSTANCE_ID", config.INSTANCE_ID
        )

    # ------------------------------------------------------------------ #
    def set_up_permissions(self) -> None:
        # Least-privilege: accounts + products read-only; cards reads and writes.
        self.tables.accounts.grant_read_data(self.lambdas.accounts)
        self.tables.products.grant_read_data(self.lambdas.products)
        self.tables.cards.grant_read_write_data(self.lambdas.cards)

        # ai_session: read accounts (phone/email GSIs) + write the customer
        # record into the Q in Connect (Wisdom) session. UpdateSessionData is
        # granted under both action namespaces (boto3 "qconnect" calls it; the
        # service authorizes under the legacy "wisdom:" prefix), scoped to the
        # assistant's sessions.
        self.tables.accounts.grant_read_data(self.lambdas.ai_session)
        self.lambdas.ai_session.add_to_role_policy(
            iam.PolicyStatement(
                actions=["wisdom:UpdateSessionData", "qconnect:UpdateSessionData"],
                resources=[
                    f"arn:aws:wisdom:{self.region}:{self.account}:"
                    f"session/{config.ASSISTANT_ID}/*"
                ],
            )
        )
        # Discover the contact's Wisdom session ARN so the Lambda can target
        # UpdateSessionData without the flow passing it.
        self.lambdas.ai_session.add_to_role_policy(
            iam.PolicyStatement(
                actions=["connect:DescribeContact"],
                resources=[
                    f"arn:aws:connect:{self.region}:{self.account}:"
                    f"instance/{config.INSTANCE_ID}/contact/*"
                ],
            )
        )

    # ------------------------------------------------------------------ #
    def publish(self) -> None:
        """Publish the Phase 1 SSM registry consumed by later phases.

        Only the values that genuinely cross a stack boundary are published:
          * GATEWAY_ID       — bare gateway id; Phase 3 uses it as the
                               security-profile MCP application namespace.
          * MCP_TOOL_PREFIX  — "gateway_<id>__<target>___"; Phase 4 agents build
                               each MCP toolId as this prefix + operationId.
          * the products + ai_session Lambda ARNs — invoked by the Phase 5 flows.
        Everything else (gateway url, REST API id/url, accounts/cards ARNs,
        table names) is a CfnOutput only — not part of the cross-stack contract.
        """
        gid = self.gateway.gateway_id  # token: attr_gateway_identifier
        ssm_names.publish(self, "PGatewayId", ssm_names.GATEWAY_ID, gid)

        # Deploy-time token concatenation — derived from the gateway id token,
        # so nothing is known at synth (no value_from_lookup, no literal):
        # the agent toolId prefix is "gateway_<id>__<target>___".
        tool_prefix = f"gateway_{gid}__{config.AI_AGENT_MCP_TARGET}___"
        ssm_names.publish(self, "PMcpToolPrefix", ssm_names.MCP_TOOL_PREFIX, tool_prefix)

        ssm_names.publish(
            self, "PLPlan", ssm_names.LAMBDA_PLANS_ARN, self.lambdas.products.function_arn
        )
        ssm_names.publish(
            self,
            "PLSess",
            ssm_names.LAMBDA_AI_SESSION_ARN,
            self.lambdas.ai_session.function_arn,
        )

    # ------------------------------------------------------------------ #
    def create_outputs(self) -> None:
        CfnOutput(self, "RestApiId", value=self.api.rest_api_id)
        CfnOutput(self, "RestApiUrl", value=self.api.api.url)
        CfnOutput(
            self,
            "McpGatewayId",
            value=self.gateway.gateway_id,
            description="AgentCore gateway id - use as the JWT audience in Connect.",
        )
        CfnOutput(self, "McpGatewayUrl", value=self.gateway.gateway_url)
        CfnOutput(
            self,
            "ConnectDiscoveryUrl",
            value=config.OIDC_DISCOVERY_URL,
            description="OIDC identity provider for the gateway JWT authorizer.",
        )
        if not config.HAS_REAL_INSTANCE:
            CfnOutput(
                self,
                "ConnectIdentityWarning",
                value=(
                    "PLACEHOLDER Connect alias in use — set INSTANCE_ALIAS in "
                    "config.py before deploying against a live Connect instance."
                ),
            )
