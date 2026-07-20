"""
agentic_cx_telco/ai_agents_stack.py — Phase 4: AI prompts + agents.

Prompts-first: this stack authors the three Orchestration AI prompts (voice,
chat, agent-assist) as CfnAIPrompt + CfnAIPromptVersion, then the three agents
that bind each published prompt version. Prompt bodies were pulled live from the
connect-chat Q in Connect domain; each prompt keeps its own model (voice/chat =
Haiku 4.5 global, assist = Sonnet global).

Agents are authored with the native CfnAIAgent (no agent version is created).
Tool input schemas carry no `maxLength` (the provider stringifies it into an
invalid JSON Schema and breaks orchestration — see cdk_constructs/connect/ai_agents.py).

Tool surfaces:
    voice  : Retrieve + 9 MCP + Escalate + Complete           (newLine confirm ON)
    chat   : voice surface + ShowNewLineGuide                 (newLine confirm OFF)
    assist : Retrieve + 9 MCP only                            (no handoff tools)

Consumes from SSM at deploy time: MCP_TOOL_PREFIX (Phase 1) and KB_ASSOC_ID
(Phase 2, the Retrieve tool binding). Publishes the three agent ARNs for Phase 5.

Agents are created as DRAFTS only ($LATEST); no agent version is published.
Assigning each agent's Connect security profile is a MANUAL post-deploy step
(Connect console / Admin website → AI agents → assign security profile). Phase 3
publishes the profile ids to SSM (SP_SELFSERVICE_ID / SP_ASSIST_ID) for that
manual step; this stack does not bind them.
"""

from __future__ import annotations

import os

from aws_cdk import CfnOutput, Stack
from constructs import Construct

import config
from cdk_constructs.connect import AgentSurface, OrchestrationAIAgent, OrchestrationPrompt
from connect.agent_tools import TOOLSET
from shared import ssm_names

# Project root, so prompt asset paths resolve regardless of cdk's cwd.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class AiAgentsStack(Stack):
    """Phase 4 — Orchestration AI prompts + agents."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        assistant_id = config.ASSISTANT_ID

        # One ORCHESTRATION prompt per agent, each on its own model.
        self.voice_prompt = OrchestrationPrompt(
            self,
            "VoicePrompt",
            assistant_id=assistant_id,
            name="telco-selfservice-voice-orchestration",
            prompt_path=os.path.join(_ROOT, config.AI_AGENT_VOICE_PROMPT),
            model_id=config.AI_AGENT_VOICE_MODEL,
            description="Telco voice self-service orchestration prompt (es-US).",
        )
        self.chat_prompt = OrchestrationPrompt(
            self,
            "ChatPrompt",
            assistant_id=assistant_id,
            name="telco-selfservice-chat-orchestration",
            prompt_path=os.path.join(_ROOT, config.AI_AGENT_CHAT_PROMPT),
            model_id=config.AI_AGENT_CHAT_MODEL,
            description="Telco chat self-service orchestration prompt (es-US).",
        )
        self.assist_prompt = OrchestrationPrompt(
            self,
            "AssistPrompt",
            assistant_id=assistant_id,
            name="telco-agent-assist-orchestration",
            prompt_path=os.path.join(_ROOT, config.AI_AGENT_ASSIST_PROMPT),
            model_id=config.AI_AGENT_ASSIST_MODEL,
            description="Telco agent-assistance orchestration prompt (es-US).",
        )

        # Agents are instance-bound (connectInstanceArn) and consume the live
        # gateway/KB ids from SSM — only built when a real instance is set.
        if config.HAS_REAL_INSTANCE:
            self._create_agents(assistant_id)

        # CloudWatch logging for the assistant's AI-agent events (EVENT_LOGS) is
        # NOT provisioned here. ASSISTANT_ID is the Q in Connect AI Agents
        # domain SHARED across every industry project on this account, and
        # CloudWatch Logs allows only one EVENT_LOGS delivery source per
        # resource — a second stack creating its own delivery source against
        # the same assistant hits a ConflictException. The vended-log delivery
        # is provisioned ONCE in the shared `general-localization` (CX-LANG-UTILS)
        # app instead; see that project's connect/ai_agent_logging.py.

        # Human/ops outputs — the published prompt version ids.
        CfnOutput(self, "VoicePromptVersionId", value=self.voice_prompt.ai_prompt_version_id)
        CfnOutput(self, "ChatPromptVersionId", value=self.chat_prompt.ai_prompt_version_id)
        CfnOutput(self, "AssistPromptVersionId", value=self.assist_prompt.ai_prompt_version_id)

    # ------------------------------------------------------------------ #
    def _create_agents(self, assistant_id: str) -> None:
        connect_instance_arn = (
            f"arn:aws:connect:{self.region}:{self.account}:instance/{config.INSTANCE_ID}"
        )

        # Consume the cross-stack inputs (deploy-time tokens).
        mcp_tool_prefix = ssm_names.consume(self, ssm_names.MCP_TOOL_PREFIX)
        kb_assoc_id = ssm_names.consume(self, ssm_names.KB_ASSOC_ID)

        common = dict(
            assistant_id=assistant_id,
            connect_instance_arn=connect_instance_arn,
            locale=config.AI_AGENT_LOCALE,
            toolset=TOOLSET,
            assistant_association_id=kb_assoc_id,
            mcp_tool_prefix=mcp_tool_prefix,
            content_language_key=config.KB_LANGUAGE_TAG_KEY,
            content_language=config.AI_AGENT_CONTENT_LANGUAGE,
        )

        self.voice_agent = OrchestrationAIAgent(
            self,
            "VoiceAgent",
            agent_name="telco-selfservice-voice-es",
            prompt_version_id=self.voice_prompt.ai_prompt_version_id,
            surface=AgentSurface.VOICE,
            description="Telco voice-first self-service orchestration agent (es-US).",
            **common,
        )
        self.voice_agent.node.add_dependency(self.voice_prompt)

        self.chat_agent = OrchestrationAIAgent(
            self,
            "ChatAgent",
            agent_name="telco-selfservice-chat-es",
            prompt_version_id=self.chat_prompt.ai_prompt_version_id,
            surface=AgentSurface.CHAT,
            description="Telco chat-first self-service orchestration agent (es-US).",
            **common,
        )
        self.chat_agent.node.add_dependency(self.chat_prompt)

        self.assist_agent = OrchestrationAIAgent(
            self,
            "AssistAgent",
            agent_name="telco-agent-assist-es",
            prompt_version_id=self.assist_prompt.ai_prompt_version_id,
            surface=AgentSurface.ASSIST,
            description="Telco agent-assistance orchestration agent (es-US).",
            **common,
        )
        self.assist_agent.node.add_dependency(self.assist_prompt)

        # Publish the agent ARNs for Phase 5 (contact flows bind these).
        ssm_names.publish(self, "PAgentVoice", ssm_names.AGENT_VOICE_ARN, self.voice_agent.ai_agent_arn)
        ssm_names.publish(self, "PAgentChat", ssm_names.AGENT_CHAT_ARN, self.chat_agent.ai_agent_arn)
        ssm_names.publish(self, "PAgentAssist", ssm_names.AGENT_ASSIST_ARN, self.assist_agent.ai_agent_arn)

        CfnOutput(self, "VoiceAgentArn", value=self.voice_agent.ai_agent_arn)
        CfnOutput(self, "ChatAgentArn", value=self.chat_agent.ai_agent_arn)
        CfnOutput(self, "AssistAgentArn", value=self.assist_agent.ai_agent_arn)

        # Security-profile assignment to each agent is a MANUAL post-deploy step
        # (Connect console / Admin website → AI agents → assign security
        # profile). Phase 3 publishes SP_SELFSERVICE_ID / SP_ASSIST_ID to SSM
        # for that step; this stack intentionally does not bind them, so the
        # agents remain plain drafts ($LATEST).
