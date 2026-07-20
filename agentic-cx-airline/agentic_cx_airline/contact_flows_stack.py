"""
agentic_cx_airline/contact_flows_stack.py — Phase 5: contact flow modules + flows.

The full inbound + escalation chain, CDK-managed:

    inbound flow ──FlowModuleId──▶ set-customer-session-airline module ─▶ ai_session Lambda
                 ──FlowModuleId──▶ airline-escalate-to-agent module ─DefaultAgentUI▶ screen-pop flow ─▶ handoff view
                 ──GetCustomerInput▶ Lex bot
                 ──CreateWisdomSession / Set AI agent▶ voice / chat / assist agents

All cross-stack references are resolved from `*_PLACEHOLDER` markers at synth:
    HANDOFF_VIEW_ARN_PLACEHOLDER           -> handoff view (created here)
    SCREENPOP_FLOW_ARN_PLACEHOLDER         -> screen-pop flow (this stack)
    ESCALATE_MODULE_ID_PLACEHOLDER         -> escalate module id (Fn.split of its ARN)
    SET_CUSTOMER_SESSION_MODULE_ID_PLACEHOLDER -> set-session module id
    INIT_MODULE_ID_PLACEHOLDER             -> external init-flow-es module id
    NEWLINE_VIEW_ARN_PLACEHOLDER           -> SSM VIEW_NEWLINE_ARN (Phase 3)
    AI_SESSION_LAMBDA_ARN_PLACEHOLDER      -> SSM LAMBDA_AI_SESSION_ARN (Phase 1)
    ASSISTANT_ARN_PLACEHOLDER              -> config.ASSISTANT_ID assistant ARN
    VOICE/CHAT/ASSIST_AGENT_LATEST_ARN_PLACEHOLDER -> SSM AGENT_*_ARN (Phase 4).
        CfnAIAgent.attr_ai_agent_arn already returns the ARN qualified to
        ":$LATEST", so it is used as-is — do NOT append another ":$LATEST"
        (that yields ":$LATEST:$LATEST" -> InvalidContactFlowException).
    LEX_BOT_ALIAS_ARN_PLACEHOLDER          -> SSM LEX_BOT_ALIAS_ARN (Phase 3 publish)
    BASIC_QUEUE_ARN_PLACEHOLDER            -> queue ARN resolved at deploy time

BasicQueue: queue ids are unique per instance, so a literal ARN from the source
instance cannot deploy elsewhere (Connect rejects it: "Failed to convert id").
The ARN is resolved at DEPLOY time by NAME (config.BASIC_QUEUE_NAME) via the
BasicQueueLookup connect:ListQueues custom resource, so the flow tracks whatever
instance you deploy to with no manual step. Pin config.BASIC_QUEUE_ID to skip
the lookup and use a specific queue. The ai_session/plans Lambda↔Connect
associations live in Phase 1, so the flows can invoke them.
"""

from __future__ import annotations

import os

from aws_cdk import CfnOutput, Fn, Stack
from constructs import Construct

import config
from cdk_constructs.connect import (
    BasicQueueLookup,
    ContactFlow,
    ContactFlowModule,
    CustomerManagedView,
)
from shared import ssm_names

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _module_id(module_arn: str) -> str:
    """Derive a flow-module id from its ARN (.../flow-module/<id>)."""
    return Fn.select(1, Fn.split("/flow-module/", module_arn))


class ContactFlowsStack(Stack):
    """Phase 5 — set-customer-session + escalate modules, screen-pop + inbound flows."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        if not config.HAS_REAL_INSTANCE:
            # Instance-bound stack — nothing to synthesize without a real instance.
            return

        instance_arn = (
            f"arn:aws:connect:{self.region}:{self.account}:instance/{config.INSTANCE_ID}"
        )
        assistant_arn = (
            f"arn:aws:wisdom:{self.region}:{self.account}:assistant/{config.ASSISTANT_ID}"
        )
        # BasicQueue ARN scoped to THIS instance (queue ids are per-instance, so
        # the source instance's literal ARN can't deploy here). If a specific
        # queue id is pinned in config, build the ARN directly; otherwise resolve
        # it by name at DEPLOY time via a connect:ListQueues custom resource.
        if config.BASIC_QUEUE_ID:
            basic_queue_arn = (
                f"arn:aws:connect:{self.region}:{self.account}:"
                f"instance/{config.INSTANCE_ID}/queue/{config.BASIC_QUEUE_ID}"
            )
        else:
            self.basic_queue = BasicQueueLookup(
                self,
                "BasicQueueLookup",
                instance_id=config.INSTANCE_ID,
                queue_name=config.BASIC_QUEUE_NAME,
            )
            basic_queue_arn = self.basic_queue.queue_arn

        # --- consume cross-stack values (deploy-time) ---
        l_ai_session = ssm_names.consume(self, ssm_names.LAMBDA_AI_SESSION_ARN)
        view_newline = ssm_names.consume(self, ssm_names.VIEW_NEWLINE_ARN)
        voice_arn = ssm_names.consume(self, ssm_names.AGENT_VOICE_ARN)
        chat_arn = ssm_names.consume(self, ssm_names.AGENT_CHAT_ARN)
        assist_arn = ssm_names.consume(self, ssm_names.AGENT_ASSIST_ARN)
        lex_bot_alias = ssm_names.consume(self, ssm_names.LEX_BOT_ALIAS_ARN)
        # init-flow-es MODULE arn — created + published by CX-LANG-UTILS
        # (general-localization). The inbound flow invokes it as its very first
        # (Start) action; it sets logging/recording behavior and the customer
        # queue event hook. Deploy CX-LANG-UTILS first so this resolves.
        init_module_arn = ssm_names.consume(self, ssm_names.INIT_FLOW_MODULE_ARN)

        # --- handoff view (rendered by the screen-pop flow) ---
        self.handoff_view = CustomerManagedView(
            self,
            "EscalationHandoffView",
            instance_arn=instance_arn,
            name=config.ESCALATION_HANDOFF_VIEW_NAME,
            content_path=os.path.join(_ROOT, config.ESCALATION_HANDOFF_VIEW_CONTENT),
            actions=["Submit"],
            description="Airline escalation hand-off screen-pop view.",
        )

        # --- screen-pop flow (references the handoff view) ---
        self.screenpop = ContactFlow(
            self,
            "ScreenPopFlow",
            instance_arn=instance_arn,
            name="airline-agent-screenpop-es",
            flow_path=os.path.join(_ROOT, config.FLOW_SCREENPOP),
            flow_type="CONTACT_FLOW",
            description="DefaultAgentUI screen-pop mounting the handoff view (CDK-managed).",
            replacements={
                "HANDOFF_VIEW_ARN_PLACEHOLDER": self.handoff_view.view_qualified_arn,
            },
        )
        self.screenpop.node.add_dependency(self.handoff_view)

        # --- escalate-to-agent module (DefaultAgentUI -> screen-pop) ---
        self.escalate_module = ContactFlowModule(
            self,
            "EscalateModule",
            instance_arn=instance_arn,
            name="airline-escalate-to-agent",
            flow_path=os.path.join(_ROOT, config.FLOW_ESCALATE_MODULE),
            description="Registers the screen-pop as DefaultAgentUI, sets the queue, transfers.",
            replacements={
                "SCREENPOP_FLOW_ARN_PLACEHOLDER": self.screenpop.flow_arn,
                "BASIC_QUEUE_ARN_PLACEHOLDER": basic_queue_arn,
            },
        )
        self.escalate_module.node.add_dependency(self.screenpop)

        # --- set-customer-session-airline module (invokes ai_session Lambda) ---
        self.set_session_module = ContactFlowModule(
            self,
            "SetCustomerSessionModule",
            instance_arn=instance_arn,
            name="set-customer-session-airline",
            flow_path=os.path.join(_ROOT, config.FLOW_SET_CUSTOMER_SESSION),
            description="Classifies the endpoint, looks the customer up, writes the Q in Connect session.",
            replacements={
                "AI_SESSION_LAMBDA_ARN_PLACEHOLDER": l_ai_session,
            },
        )

        # --- inbound self-service flow (references both modules + agents + lex) ---
        self.inbound = ContactFlow(
            self,
            "InboundFlow",
            instance_arn=instance_arn,
            name="airline-selfservice-es-inbound",
            flow_path=os.path.join(_ROOT, config.FLOW_INBOUND),
            flow_type="CONTACT_FLOW",
            description="Airline Spanish self-service inbound voice flow (CDK-managed).",
            replacements={
                "ESCALATE_MODULE_ID_PLACEHOLDER": _module_id(self.escalate_module.module_arn),
                "SET_CUSTOMER_SESSION_MODULE_ID_PLACEHOLDER": _module_id(self.set_session_module.module_arn),
                "INIT_MODULE_ID_PLACEHOLDER": _module_id(init_module_arn),
                "NEWLINE_VIEW_ARN_PLACEHOLDER": view_newline,
                "AI_SESSION_LAMBDA_ARN_PLACEHOLDER": l_ai_session,
                "ASSISTANT_ARN_PLACEHOLDER": assistant_arn,
                "VOICE_AGENT_LATEST_ARN_PLACEHOLDER": voice_arn,
                "CHAT_AGENT_LATEST_ARN_PLACEHOLDER": chat_arn,
                "ASSIST_AGENT_LATEST_ARN_PLACEHOLDER": assist_arn,
                "LEX_BOT_ALIAS_ARN_PLACEHOLDER": lex_bot_alias,
                "BASIC_QUEUE_ARN_PLACEHOLDER": basic_queue_arn,
            },
        )
        self.inbound.node.add_dependency(self.escalate_module)
        self.inbound.node.add_dependency(self.set_session_module)

        # --- outputs ---
        CfnOutput(self, "ScreenPopFlowArn", value=self.screenpop.flow_arn)
        CfnOutput(self, "EscalateModuleArn", value=self.escalate_module.module_arn)
        CfnOutput(self, "SetCustomerSessionModuleArn", value=self.set_session_module.module_arn)
        CfnOutput(self, "InboundFlowArn", value=self.inbound.flow_arn)
        CfnOutput(self, "EscalationHandoffViewArn", value=self.handoff_view.view_qualified_arn)
