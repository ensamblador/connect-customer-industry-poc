"""
cdk_constructs/connect/ai_prompts.py — Q in Connect Orchestration AI prompts as CDK.

Phase 4 (prompts-first): each agent runs a versioned ORCHESTRATION prompt
authored as `CfnAIPrompt` + a published `CfnAIPromptVersion`. The prompt bodies
were pulled live from the running Q in Connect domain (the authoritative
source) and stored under `connect_ai_agents/<agent>/prompts/*.yaml`; this
construct loads a body verbatim and publishes it on the configured model.

Each prompt keeps its OWN model (voice/chat = Haiku 4.5 global, assist =
Sonnet global) — the model is not forced to a single value. The `<sources>`
citation behavior is NOT part of the orchestration body; it is enforced by the
system Retrieve tool configured on the agent, so the captured body is used
as-is.

The `CfnAIPromptVersion` logical id embeds a short content hash of the body +
model so that editing the prompt body (or swapping the model) publishes a new
immutable version instead of mutating the existing one.
"""

from __future__ import annotations

import hashlib

from aws_cdk import aws_wisdom as wisdom
from constructs import Construct


def _content_hash(*parts: str) -> str:
    """Short stable hash of the given parts, for version logical ids."""
    h = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return h[:8]


def _read_prompt(prompt_path: str) -> str:
    with open(prompt_path, "r", encoding="utf-8") as fh:
        return fh.read()


class OrchestrationPrompt(Construct):
    """One Q in Connect ORCHESTRATION AI prompt + its published version."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        assistant_id: str,
        name: str,
        prompt_path: str,
        model_id: str,
        description: str = "",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        prompt_text = _read_prompt(prompt_path)

        self.prompt = wisdom.CfnAIPrompt(
            self,
            "Prompt",
            assistant_id=assistant_id,
            name=name,
            type="ORCHESTRATION",
            api_format="MESSAGES",
            model_id=model_id,
            template_type="TEXT",
            description=description or f"Orchestration prompt {name}.",
            template_configuration=wisdom.CfnAIPrompt.AIPromptTemplateConfigurationProperty(
                text_full_ai_prompt_edit_template_configuration=wisdom.CfnAIPrompt.TextFullAIPromptEditTemplateConfigurationProperty(
                    text=prompt_text,
                )
            ),
        )
        # New immutable version whenever the body or model changes.
        self.prompt_version = wisdom.CfnAIPromptVersion(
            self,
            f"PromptVersion{_content_hash(prompt_text, model_id)}",
            assistant_id=assistant_id,
            ai_prompt_id=self.prompt.attr_ai_prompt_id,
        )

    @property
    def ai_prompt_id(self) -> str:
        """The unversioned prompt id."""
        return self.prompt.attr_ai_prompt_id

    @property
    def ai_prompt_version_id(self) -> str:
        """The published version qualified id (<id>:<version>) an agent binds to."""
        return self.prompt_version.attr_ai_prompt_version_id
