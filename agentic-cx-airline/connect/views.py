"""
connect/views.py — Amazon Connect customer-managed views as CDK.

Following the project convention, ALL `aws_connect` view constructs live here.
A customer-managed view is `connect.CfnView`; it renders in the customer's chat
window via a "Show view" (`ShowView`) flow block. We keep the authored view
JSON in `views/<name>/view-content.json` and load it verbatim, so the repo file
stays the single source of truth and the console import /
`validate_view_json` round-trip.

Shape note — `view-content.json` vs `CfnView`:
The authored `view-content.json` is the full CreateView/UpdateView `Content`
payload: `{ "Template": {...}, "Actions": [...] }`. That whole document is what
`validate_view_json` checks and what a console "import" expects. CloudFormation's
`AWS::Connect::View`, however, splits that single payload into two *separate*
properties: `Template` (the Head/Body structure) and `Actions` (the button
list). So we pass the file's top-level `Template` object to `CfnView.template`
and the actions list to `CfnView.actions`. Passing the whole `{Template,
Actions}` document as `template` (and `actions` again separately) would nest a
stray `Actions` key inside the template and double-count the actions — so we
deliberately extract `content["Template"]` here.

Version pinning — `ShowView` references a view by its *qualified* ARN (a
published version). We expose `view_qualified_arn` pinned to `:$LATEST` to match
the existing screen-pop convention (always serve the most recently published
content); switch to a numbered version here if a change ever needs staged
rollout.
"""

from __future__ import annotations

import json
from typing import Any

from aws_cdk import aws_connect as connect
from constructs import Construct


def _load_template(content_path: str) -> Any:
    """Load a view-content.json and return just its `Template` structure.

    Accepts the full `{ "Template": ..., "Actions": ... }` payload (the common
    case) and returns the `Template` object for `CfnView.template`. If a file
    only carries the bare template (no top-level `Template` key), it is passed
    through unchanged.

    The `Template` value may be either a JSON object (CloudFormation's
    `CfnView.template` shape) or a JSON-encoded string (the CreateView/
    UpdateView API and console-export shape). CFN needs the object form, so a
    stringified template is parsed back into an object here.
    """
    with open(content_path, "r", encoding="utf-8") as fh:
        content = json.load(fh)
    template = content["Template"] if isinstance(content, dict) and "Template" in content else content
    if isinstance(template, str):
        template = json.loads(template)
    return template


class CustomerManagedView(Construct):
    """A customer-managed Connect view loaded from a view-content.json file."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        instance_arn: str,
        name: str,
        content_path: str,
        actions: list[str],
        description: str = "",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.view = connect.CfnView(
            self,
            "Resource",
            instance_arn=instance_arn,
            name=name,
            actions=actions,
            template=_load_template(content_path),
            description=description or None,
        )

    @property
    def view_arn(self) -> str:
        """The unqualified view ARN (no version suffix)."""
        return self.view.attr_view_arn

    @property
    def view_qualified_arn(self) -> str:
        """The qualified view ARN pinned to `$LATEST` for `ShowView`."""
        return f"{self.view.attr_view_arn}:$LATEST"
