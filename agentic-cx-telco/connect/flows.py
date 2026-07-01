"""
connect/flows.py — Amazon Connect contact flows (and flow modules) as CDK.

Following the project convention, ALL `aws_connect` flow constructs live here.
A contact flow is `connect.CfnContactFlow`; its `content` is the Connect Flow
language JSON (the same document `create-contact-flow --content` takes). We keep
the authored JSON in `projects/telco-cx/flows/<name>/flow.json` and load it
verbatim, so the repo file stays the single source of truth and the designer
export round-trips.

Optional templating: a flow's JSON often embeds ARNs (the instance, a view, a
queue, the AI-agents domain). When those should track CDK-created resources,
pass `replacements={"<MARKER>": <token-or-arn>}` and author the JSON with the
markers; `str.replace` swaps them at synth. When the referenced resources are
pre-existing (the common case here — the view, Lex bot, queue and AI agents are
already live), the JSON can carry their literal ARNs and no replacement is
needed.

NOTE on names: `CfnContactFlow` names are unique per instance. A flow created
here with the same name as a manually-created live flow collides
("DuplicateResourceException"). To bring a hand-built flow under CDK control,
delete the manual one first (or give the CDK flow a distinct name and re-point
references to it).
"""

from __future__ import annotations

import os

from aws_cdk import aws_connect as connect
from constructs import Construct


def _load(flow_path: str, replacements: dict[str, str] | None = None) -> str:
    with open(flow_path, "r", encoding="utf-8") as fh:
        content = fh.read()
    for marker, value in (replacements or {}).items():
        content = content.replace(marker, value)
    return content


class ContactFlow(Construct):
    """A Connect contact flow loaded from a Flow-language JSON file."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        instance_arn: str,
        name: str,
        flow_path: str,
        flow_type: str = "CONTACT_FLOW",
        description: str = "",
        replacements: dict[str, str] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.flow = connect.CfnContactFlow(
            self,
            "Resource",
            instance_arn=instance_arn,
            name=name,
            type=flow_type,
            content=_load(flow_path, replacements),
            description=description or None,
        )

    @property
    def flow_arn(self) -> str:
        return self.flow.attr_contact_flow_arn

    @property
    def flow_ref(self) -> str:
        return self.flow.ref


class ContactFlowModule(Construct):
    """A reusable Connect flow module loaded from a Flow-language JSON file."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        instance_arn: str,
        name: str,
        flow_path: str,
        description: str = "",
        replacements: dict[str, str] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.module = connect.CfnContactFlowModule(
            self,
            "Resource",
            instance_arn=instance_arn,
            name=name,
            content=_load(flow_path, replacements),
            description=description or None,
        )

    @property
    def module_arn(self) -> str:
        return self.module.attr_contact_flow_module_arn
