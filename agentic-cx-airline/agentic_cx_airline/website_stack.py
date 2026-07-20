"""
agentic_cx_airline/website_stack.py — Phase 6: the static "AeroLatam" website.

Final, independent phase. Deploys the Vite-built site (website/dist) to a
private S3 bucket served through CloudFront with Origin Access Control (OAC),
reusing the shared, industry-agnostic ``cdk_constructs.webhosting.Webhosting``
construct. This stack is a thin wrapper: it reads the airline ``config`` and
passes the industry values (asset paths, table names, CloudFront knobs) into
the shared construct.

The site hosts the Amazon Connect chat widget and passes the logged-in email
as a contact attribute, so it complements the chat self-service + agent-assist
path. It also exposes a demo data viewer at ``/datos`` (a Lambda behind a
CloudFront behavior) that renders the three Phase 1 DynamoDB tables
(accounts/products/cards) as HTML. Because that Lambda reads those tables at
runtime, the stack is ordered after CX-AIRLINE-MCP (ordering-only edge — the
table ARNs are reconstructed from config names, no SSM/Fn::ImportValue).

Operational note — the Connect widget configuration is baked into the built
assets, so there are no runtime VITE_* env vars. The construct's only synth
check is that website/dist exists; build the site first:

    cd website && npm install && npm run build

Gated by config.BUILD_WEBSITE: turn it off to synthesize an empty stack
(e.g. when website/dist has not been built yet).
"""

from __future__ import annotations

from aws_cdk import Stack
from constructs import Construct

import config
from cdk_constructs.webhosting import Webhosting


class WebsiteStack(Stack):
    """Phase 6 — static website hosting (S3 private + CloudFront OAC)."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # The construct validates that website/dist exists at synth time, so
        # gate on BUILD_WEBSITE to allow an empty synth before the site is
        # built. All config→props wiring lives in Webhosting.from_config.
        if config.BUILD_WEBSITE:
            self.webhosting = Webhosting.from_config(self, "Webhosting", config=config)
