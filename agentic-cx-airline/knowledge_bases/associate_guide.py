#!/usr/bin/env python3
"""
associate_guide.py — bind THIS project's step-by-step GUIDE contact flow to its
Q in Connect (Wisdom) knowledge-base article(s) via AMAZON_CONNECT_GUIDE content
associations.

This is the single, industry-agnostic guide-association script shared by every
industry project in this repo. It performs the association that CORRESPONDS to
the current project, resolving everything from that project's `config.py` via
the standard guide constants:

  * ``GUIDE_FLOW_NAME``     — the guide contact flow's name (button label);
  * ``GUIDE_CONTENT_MATCH`` — the title/name substring identifying the guide
    article(s) in the knowledge base.

So the SAME file drops into each project and "does the corresponding
associations" for that industry (whichever step-by-step guide that project
provisions — e.g. an activation guide or a claim/report guide).

WHY THIS IS A SCRIPT (not a CDK custom resource)
------------------------------------------------
The EXTERNAL S3 crawler creates a NEW content item (new contentId) for every
object it ingests, and the guide article exists once PER LANGUAGE (es/pt/en). So
the content ids only exist AFTER the asynchronous KB sync, and they change on
every re-sync — awkward to express as a deploy-time CloudFormation resource (it
would need post-ingestion ids hand-copied into config). Like KB tagging
(`tag_kb_content.py`), the association is therefore an OPERATIONAL step that runs
AFTER ingestion: deploy the stack (which builds the guide view + guide flow),
sync the KB, then run this script.

WHAT IT DOES
------------
1. Resolves the knowledge-base id (from SSM `KB_ID`, or --kb-id) and the guide
   flow ARN (resolved by NAME from config — via connect:ListContactFlows for
   config.INSTANCE_ID, or --flow-arn).
2. `list-contents` on the KB and selects EVERY item whose title/name contains
   the match substring (all languages of the guide article).
3. For each match, creates an AMAZON_CONNECT_GUIDE association to the guide flow,
   IDEMPOTENTLY: if an AMAZON_CONNECT_GUIDE association already points at the
   flow it is left untouched; if it points elsewhere it is deleted and
   recreated (Q in Connect allows only ONE association per content and has no
   UpdateContentAssociation). This mirrors the logic of the custom-resource
   Lambda this script replaces.
4. Prints a per-item summary.

USAGE
-----
    # from this directory (knowledge_bases/), with the venv active
    python associate_guide.py --profile connect-industry --region us-east-1
    python associate_guide.py --kb-id <id> --flow-arn <arn>   # skip lookups
    python associate_guide.py --match <substr> --dry-run      # preview only

Requires boto3 and AWS credentials (via --profile or the environment).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys

import boto3

# config.py + shared/ssm_names.py live at the CDK app root (the parent of this
# knowledge_bases/ directory); put it on sys.path so we can import them.
_HERE = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.dirname(_HERE)
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)

import config  # noqa: E402
from shared import ssm_names  # noqa: E402

GUIDE = "AMAZON_CONNECT_GUIDE"


# --------------------------------------------------------------------------- #
# Config resolution — every project's config.py defines the SAME standard guide
# constants, so the identical file drops into each project unchanged.
# --------------------------------------------------------------------------- #
def guide_flow_name() -> str:
    """The guide flow NAME this project provisions (config.GUIDE_FLOW_NAME)."""
    return getattr(config, "GUIDE_FLOW_NAME", "") or ""


def guide_content_match() -> str:
    """The KB title/name substring for this project's guide article(s)
    (config.GUIDE_CONTENT_MATCH)."""
    return getattr(config, "GUIDE_CONTENT_MATCH", "") or ""


# --------------------------------------------------------------------------- #
# Resolution helpers.
# --------------------------------------------------------------------------- #
def _resolve_kb_id(ssm_client, explicit: str | None) -> str:
    if explicit:
        return explicit
    try:
        return ssm_client.get_parameter(Name=ssm_names.KB_ID)["Parameter"]["Value"]
    except Exception as exc:
        sys.exit(
            f"Could not resolve the knowledge-base id from SSM ({ssm_names.KB_ID}): "
            f"{exc}\nPass --kb-id explicitly."
        )


def _resolve_flow_arn(connect_client, instance_id: str, flow_name: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    if not instance_id:
        sys.exit("No instance id (config.INSTANCE_ID is empty); pass --flow-arn explicitly.")
    paginator = connect_client.get_paginator("list_contact_flows")
    for page in paginator.paginate(InstanceId=instance_id):
        for flow in page.get("ContactFlowSummaryList", []):
            if flow.get("Name") == flow_name:
                return flow["Arn"]
    sys.exit(
        f"Contact flow {flow_name!r} not found in instance {instance_id}. Has the "
        "Phase 3 ConnectSupport stack been deployed? Pass --flow-arn to override."
    )


def _client_token(kb_id: str, content_id: str, flow_arn: str) -> str:
    """Stable idempotency token (mirrors the old custom-resource Lambda)."""
    seed = f"{kb_id}|{content_id}|{flow_arn}".encode("utf-8")
    return hashlib.sha256(seed).hexdigest()


def _guide_flow_id(assoc: dict | None) -> str | None:
    """The flowId an AMAZON_CONNECT_GUIDE association points at, or None."""
    data = (assoc or {}).get("associationData") or {}
    guide = data.get("amazonConnectGuideAssociation") or {}
    return guide.get("flowId")


def _existing_guide_association(qc, kb_id: str, content_id: str) -> dict | None:
    """Return the content's existing AMAZON_CONNECT_GUIDE association, or None."""
    next_token = None
    while True:
        kwargs = dict(knowledgeBaseId=kb_id, contentId=content_id)
        if next_token:
            kwargs["nextToken"] = next_token
        resp = qc.list_content_associations(**kwargs)
        for summary in resp.get("contentAssociationSummaries", []):
            if summary.get("associationType") == GUIDE:
                return summary
        next_token = resp.get("nextToken")
        if not next_token:
            return None


def _list_guide_contents(qc, kb_id: str, match: str) -> list[dict]:
    """Return content items whose title or name contains ``match`` (case-insensitive)."""
    needle = match.lower()
    out: list[dict] = []
    paginator = qc.get_paginator("list_contents")
    for page in paginator.paginate(knowledgeBaseId=kb_id):
        for item in page.get("contentSummaries", []):
            haystack = f"{item.get('title', '')} {item.get('name', '')}".lower()
            if needle in haystack:
                out.append(item)
    return out


# --------------------------------------------------------------------------- #
# Association (idempotent), mirroring the replaced Lambda's behavior.
# --------------------------------------------------------------------------- #
def _associate(qc, kb_id: str, content_id: str, flow_arn: str, dry_run: bool) -> str:
    """Ensure exactly one AMAZON_CONNECT_GUIDE association -> flow_arn. Returns a
    short status string: 'exists' | 'replaced' | 'created' | 'would-create'."""
    existing = _existing_guide_association(qc, kb_id, content_id)
    if existing is not None and _guide_flow_id(existing) == flow_arn:
        return "exists"

    if dry_run:
        return "would-replace" if existing is not None else "would-create"

    status = "created"
    if existing is not None:
        qc.delete_content_association(
            knowledgeBaseId=kb_id,
            contentId=content_id,
            contentAssociationId=existing["contentAssociationId"],
        )
        status = "replaced"

    resp = qc.create_content_association(
        knowledgeBaseId=kb_id,
        contentId=content_id,
        associationType=GUIDE,
        association={"amazonConnectGuideAssociation": {"flowId": flow_arn}},
        clientToken=_client_token(kb_id, content_id, flow_arn),
    )
    assoc = resp["contentAssociation"]
    if _guide_flow_id(assoc) != flow_arn:
        sys.exit(
            f"Association for content {content_id} did not resolve to the expected "
            f"flow: expected {flow_arn!r}, got {_guide_flow_id(assoc)!r}."
        )
    return status


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Associate this project's step-by-step guide flow with its KB "
        "content (AMAZON_CONNECT_GUIDE)."
    )
    ap.add_argument("--kb-id", help="Knowledge base id (default: from SSM KB_ID).")
    ap.add_argument("--flow-arn", help="Guide flow ARN (default: resolved by name).")
    ap.add_argument("--instance-id", help="Connect instance id (default: config.INSTANCE_ID).")
    ap.add_argument("--flow-name", help="Guide flow name (default: resolved from config).")
    ap.add_argument("--match", help="Title/name substring to match (default: resolved from config).")
    ap.add_argument("--region", help="AWS region (default: AWS_REGION / profile default).")
    ap.add_argument("--profile", help="AWS profile (default: environment).")
    ap.add_argument("--dry-run", action="store_true", help="Show what would be associated; make no changes.")
    args = ap.parse_args()

    instance_id = args.instance_id or getattr(config, "INSTANCE_ID", "")
    flow_name = args.flow_name or guide_flow_name()
    match = args.match or guide_content_match()
    region = args.region or os.getenv("AWS_REGION")

    if not flow_name:
        sys.exit(
            "No guide flow name configured. Define GUIDE_FLOW_NAME in config.py, "
            "or pass --flow-name."
        )
    if not match:
        sys.exit(
            "No guide content match configured. Define GUIDE_CONTENT_MATCH "
            "in config.py, or pass --match."
        )

    session = boto3.Session(profile_name=args.profile) if args.profile else boto3.Session()
    qc = session.client("qconnect", region_name=region)
    connect_client = session.client("connect", region_name=region)
    ssm_client = session.client("ssm", region_name=region)

    kb_id = _resolve_kb_id(ssm_client, args.kb_id)
    flow_arn = _resolve_flow_arn(connect_client, instance_id, flow_name, args.flow_arn)

    print(f"KB:        {kb_id}")
    print(f"flow:      {flow_name}")
    print(f"flow ARN:  {flow_arn}")
    print(f"match:     title/name contains {match!r}")
    if args.dry_run:
        print("mode:      DRY RUN (no changes)\n")

    contents = _list_guide_contents(qc, kb_id, match)
    if not contents:
        sys.exit(
            f"No content items match {match!r} in KB {kb_id}. Has the KB finished "
            "its first sync? (See tag_kb_content.py --wait.)"
        )

    counts: dict[str, int] = {}
    for item in contents:
        content_id = item["contentId"]
        title = item.get("title") or item.get("name") or content_id
        status = _associate(qc, kb_id, content_id, flow_arn, args.dry_run)
        counts[status] = counts.get(status, 0) + 1
        print(f"  [{status:>13}] {title} ({content_id})")

    summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    print(f"\nDone. {len(contents)} guide content item(s): {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
