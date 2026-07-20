"""
agentic_cx_airline/connect_support_stack.py — Phase 3: Connect supporting resources.

Merged stack for the Connect resources the AI agents (Phase 4) and contact flows
(Phase 5) depend on, but which are siblings of each other:

  * AI-agent security profiles (self-service + agent-assist) — least-privilege
    Wisdom.View + CustomViews.Access, plus the MCP tool grant built at deploy
    time from the gateway id.
  * Customer-managed views — the card-request guided form and the activate-card
    guide.
  * The activate-card guide contact flow (the AMAZON_CONNECT_GUIDE content
    association that binds it to the KB content is created post-deploy by
    knowledge_bases/associate_guide.py — see that script).

Cross-stack inputs (consumed from SSM at deploy time):
    GATEWAY_ID  (Phase 1) — the bare gateway id == the security-profile MCP
                            application namespace.

Published for later phases:
    SP_SELFSERVICE_ID / SP_ASSIST_ID — the AI-agent security profile ids,
                                       published for the MANUAL post-deploy
                                       agent assignment (see the README).
    VIEW_NEWLINE_ARN                 — Phase 5 inbound flow ShowView block.

Ordering: depends on Phase 1 (so the gateway target's live tool list exists
before Connect validates the security-profile `<target>___<op>` grant). The
edge is declared in app.py.

Note — the activate-card guide content associations are NOT created by this
stack. The content ids are POST-INGESTION values (the EXTERNAL crawler assigns a
fresh id per object on every sync), so binding them is an operational,
post-deploy step like KB tagging: run
knowledge_bases/associate_guide.py after the KB syncs. It resolves
the guide flow by name and the activate-card content by title, so no content ids
are hand-maintained in config.
"""

from __future__ import annotations

import os

from aws_cdk import CfnOutput, Stack
from constructs import Construct

import config
from cdk_constructs.connect import (
    AiAgentSecurityProfile,
    ContactFlow,
    CustomerManagedView,
    QInConnectLexBot,
)
from shared import ssm_names

# Project root (where the views/ and flows/ asset folders live), so asset paths
# resolve regardless of the cwd cdk is invoked from.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ConnectSupportStack(Stack):
    """Phase 3 — security profiles + customer-managed views + activate-card guide flow."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        if not config.HAS_REAL_INSTANCE:
            # Instance-bound stack — nothing to synthesize without a real
            # Connect instance. (Phase 1/2 still synthesize their own layers.)
            return

        instance_arn = (
            f"arn:aws:connect:{self.region}:{self.account}:instance/{config.INSTANCE_ID}"
        )

        # --- consume from the SSM bus (deploy-time) ---
        gateway_id = ssm_names.consume(self, ssm_names.GATEWAY_ID)  # bare id = profile ns

        # Security-profile MCP application grant, built at deploy time from the
        # consumed gateway id: { <gateway-id>: ["<target>___<op>", ...] }.
        mcp_apps = None
        if config.BUILD_AI_AGENT_MCP_GRANT:
            mcp_apps = {
                gateway_id: [
                    f"{config.AI_AGENT_MCP_TARGET}___{op}"
                    for op in config.AI_AGENT_MCP_OPERATIONS
                ]
            }

        # --- security profiles (siblings of the views) ---
        self.sp_selfservice = AiAgentSecurityProfile(
            self,
            "AiAgentSecurityProfile",
            instance_id=config.INSTANCE_ID,
            name=config.AI_AGENT_SECURITY_PROFILE_NAME,
            permissions=config.AI_AGENT_SECURITY_PROFILE_PERMISSIONS,
            mcp_applications=mcp_apps,
            description=(
                f"Least-privilege profile for the {config.AI_AGENT_SECURITY_PROFILE_NAME} "
                "AI agent: Wisdom.View + CustomViews.Access (guides) + MCP tool grant."
            ),
            tags={"industry": "airline"},
        )
        self.sp_assist = AiAgentSecurityProfile(
            self,
            "AgentAssistSecurityProfile",
            instance_id=config.INSTANCE_ID,
            name=config.AI_AGENT_ASSIST_SECURITY_PROFILE_NAME,
            permissions=config.AI_AGENT_SECURITY_PROFILE_PERMISSIONS,
            mcp_applications=mcp_apps,
            description=(
                f"Least-privilege profile for the {config.AI_AGENT_ASSIST_SECURITY_PROFILE_NAME} "
                "AI agent (agent-assistance). Human agents using the assistant panel "
                "need the same permissions (tool calls authorize against the intersection)."
            ),
            tags={"industry": "airline"},
        )

        # --- customer-managed views (siblings of the profiles) ---
        self.view_newline = CustomerManagedView(
            self,
            "NewLineFormView",
            instance_arn=instance_arn,
            name=config.NEWLINE_VIEW_NAME,
            content_path=os.path.join(_ROOT, config.NEWLINE_VIEW_CONTENT),
            actions=["prod-tarjeta-clasica", "prod-tarjeta-oro", "prod-tarjeta-platino", "Cancel"],
            description="Airline card-request guided form for chat self-service.",
        )
        self.view_card_guide = CustomerManagedView(
            self,
            "CardGuideView",
            instance_arn=instance_arn,
            name=config.GUIDE_VIEW_NAME,
            content_path=os.path.join(_ROOT, config.GUIDE_VIEW_CONTENT),
            actions=["Previous", "Next", "End"],
            description="Airline lost-baggage step-by-step guided view, es-US.",
        )

        # --- lost-baggage guide contact flow (references the guide view) ---
        self.card_guide_flow = ContactFlow(
            self,
            "CardGuideFlow",
            instance_arn=instance_arn,
            name=config.GUIDE_FLOW_NAME,
            flow_path=os.path.join(_ROOT, config.FLOW_GUIDE),
            flow_type="CONTACT_FLOW",
            description="Airline lost-baggage step-by-step guide flow, es-US, CDK-managed.",
            replacements={
                "CARD_GUIDE_VIEW_ARN_PLACEHOLDER": self.view_card_guide.view_qualified_arn,
            },
        )
        self.card_guide_flow.node.add_dependency(self.view_card_guide)

        # --- activate-card guide content associations (AMAZON_CONNECT_GUIDE) ---
        # NOT created here. Binding the guide flow to each `activar-tarjeta` KB
        # content item is a post-deploy operational step (the content ids are
        # post-ingestion values), handled by
        # knowledge_bases/associate_guide.py. Run it after the KB
        # syncs; it resolves this flow by name (config.GUIDE_FLOW_NAME) and
        # the activate-card content by title.

        # --- Lex V2 Q-in-Connect passthrough bot (native CDK) ---
        # A Nova Sonic v2 bot whose only intent delegates to the Q in Connect
        # assistant (ASSISTANT_ID). The inbound voice flow (Phase 5)
        # hands initial speech to this bot's alias.
        assistant_arn = (
            f"arn:aws:wisdom:{self.region}:{self.account}:assistant/"
            f"{config.ASSISTANT_ID}"
        )
        self.lex_bot = QInConnectLexBot(
            self,
            "QInConnectLexBot",
            name=config.LEX_BOT_NAME,
            assistant_arn=assistant_arn,
            connect_instance_arn=instance_arn,
        )

        # --- publish the cross-stack contract ---
        ssm_names.publish(self, "PSpSelf", ssm_names.SP_SELFSERVICE_ID, self.sp_selfservice.security_profile_id)
        ssm_names.publish(self, "PSpAssist", ssm_names.SP_ASSIST_ID, self.sp_assist.security_profile_id)
        ssm_names.publish(self, "PViewNewline", ssm_names.VIEW_NEWLINE_ARN, self.view_newline.view_qualified_arn)

        # Lex bot alias ARN for the Phase 5 inbound flow — the real ARN of the
        # bot this stack just created.
        ssm_names.publish(self, "PLexBotAlias", ssm_names.LEX_BOT_ALIAS_ARN, self.lex_bot.bot_alias_arn)

        # --- human/ops outputs ---
        CfnOutput(self, "SelfServiceSecurityProfileId", value=self.sp_selfservice.security_profile_id)
        CfnOutput(self, "AssistSecurityProfileId", value=self.sp_assist.security_profile_id)
        CfnOutput(self, "NewLineFormViewArn", value=self.view_newline.view_qualified_arn)
        CfnOutput(self, "CardGuideViewArn", value=self.view_card_guide.view_qualified_arn)
        CfnOutput(self, "CardGuideFlowArn", value=self.card_guide_flow.flow_arn)
        CfnOutput(self, "LexBotAliasArn", value=self.lex_bot.bot_alias_arn)
