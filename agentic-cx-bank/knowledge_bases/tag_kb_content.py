#!/usr/bin/env python3
"""
tag_kb_content.py — tag every content item in a Q in Connect (Wisdom) knowledge
base for content segmentation.

WHY THIS IS A SCRIPT (not a CDK custom resource)
------------------------------------------------
The S3 / EXTERNAL crawler creates a NEW content item (new contentId) for every
object it ingests, and those items are created **untagged**. The AI agents'
`Retrieve` tool filters by a content tag (e.g. `industry=bank`), so after every
KB (re)build or content re-sync the freshly-ingested items must be tagged or
retrieval returns nothing.

Tagging is therefore an *operational* step that runs AFTER the asynchronous
ingestion finishes — which is awkward to express as a CloudFormation resource
(it would need to poll for an unbounded async sync inside a deploy). So content
tagging is intentionally DECOUPLED from the stack: deploy the KB with the CDK,
then run this script once ingestion completes.

WHAT IT DOES
------------
1. Resolves the knowledge-base id, region, and tags. The KB id resolves in
   order: --kb-id > manifest.json > SSM (the Phase 2 stack publishes it to
   ssm_names.KB_ID), so a fresh deploy needs no hand-copied id.
2. (optional, --wait) polls `list-contents` until at least --expect items are
   ACTIVE, so you can run it right after a deploy.
3. Derives a per-item `language` tag (es | pt | en) from each item's
   `bank/<lang>/` source path and applies it ALONGSIDE the base segmentation
   tags, so the agents' Retrieve filter can segment by language. Disable with
   --no-language.
4. Calls `tag-resource` on every content item with the combined tags.
5. Verifies and prints a per-language summary.

USAGE
-----
    # from this directory (knowledge_bases/), with the venv active.
    # AWS credentials + region come from your environment (AWS_PROFILE /
    # AWS_REGION / config), exactly like the AWS CLI — nothing is overridden.
    python tag_kb_content.py                         # kb-id from manifest, else SSM
    python tag_kb_content.py --wait --expect 21      # wait for ingestion, then tag
    python tag_kb_content.py --tags industry=bank,visibility=public
    python tag_kb_content.py --no-language           # base tags only (no language tag)
    python tag_kb_content.py --kb-id <id>            # tag a specific KB

Requires boto3 and AWS credentials (via AWS_PROFILE or the environment).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

import boto3

# config.py + shared/ssm_names.py live at the CDK app root (the parent of this
# knowledge_bases/ directory); put it on sys.path so we can import them.
_HERE = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.dirname(_HERE)
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)

from shared import ssm_names  # noqa: E402

_DEFAULT_MANIFEST = os.path.join(_HERE, "bank", "manifest.json")


def _load_manifest(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {}


def _parse_tags(raw: str | None, manifest: dict) -> dict[str, str]:
    if raw:
        out: dict[str, str] = {}
        for pair in raw.split(","):
            pair = pair.strip()
            if not pair:
                continue
            if "=" not in pair:
                sys.exit(f"Bad --tags entry '{pair}' (expected key=value).")
            k, v = pair.split("=", 1)
            out[k.strip()] = v.strip()
        return out
    # Default to the manifest's segmentation tags, then a sane fallback.
    return manifest.get("resourceTags") or {"industry": "bank", "visibility": "public"}


def _detect_language(item: dict, languages: list[str]) -> str | None:
    """Infer a content item's language from its source path segments.

    The EXTERNAL S3 crawler keys content under bank/<lang>/..., so the item's
    `name` (and, as a fallback, its `title` / `metadata` values) carries the
    language as a path segment. Returns the matched language code (e.g. "es")
    or None when no segment matches.
    """
    candidates: list[str] = []
    for key in ("name", "title"):
        value = item.get(key)
        if isinstance(value, str):
            candidates.append(value)
    metadata = item.get("metadata")
    if isinstance(metadata, dict):
        candidates.extend(v for v in metadata.values() if isinstance(v, str))

    wanted = set(languages)
    for raw in candidates:
        for segment in re.split(r"[\\/]+", raw):
            if segment in wanted:
                return segment
    return None


def _resolve_kb_id_from_ssm() -> str | None:
    """Best-effort KB id lookup from SSM (ssm_names.KB_ID), published by Phase 2.

    Returns None on any failure so the caller can fall through to its own
    "no kb-id" error with the full list of resolution options.
    """
    try:
        ssm = boto3.client("ssm")
        return ssm.get_parameter(Name=ssm_names.KB_ID)["Parameter"]["Value"]
    except Exception as exc:
        print(f"  (SSM KB id lookup failed: {exc})", file=sys.stderr)
        return None


def _resolve_kb_id(explicit: str | None, manifest: dict) -> str | None:
    """Resolve the KB id in order: explicit arg > manifest > SSM KB_ID.

    Returns the first non-empty value found (Requirement 10.7), or None when
    none of the three sources yields a value so the caller can halt with the
    "no kb-id" error (Requirement 10.8). The manifest's ``knowledgeBaseId``
    field is consulted BEFORE the SSM lookup so a manifest that pins a KB id
    wins over the Phase 2 SSM parameter.
    """
    if explicit:
        return explicit
    manifest_id = manifest.get("knowledgeBaseId")
    if manifest_id:
        return manifest_id
    return _resolve_kb_id_from_ssm()


def main() -> int:
    ap = argparse.ArgumentParser(description="Tag Q in Connect KB content for segmentation.")
    ap.add_argument("--manifest", default=_DEFAULT_MANIFEST, help="Path to the KB manifest.json.")
    ap.add_argument("--kb-id", help="Knowledge base id (default: manifest, then SSM KB_ID).")
    ap.add_argument("--tags", help="Comma-separated key=value tags (default: manifest resourceTags).")
    ap.add_argument("--language-key", default="language", help="Tag key for the per-item language (default: language).")
    ap.add_argument("--languages", default="es,pt,en", help="Comma-separated language codes to detect from the content path.")
    ap.add_argument("--no-language", action="store_true", help="Skip per-item language tagging (apply base tags only).")
    ap.add_argument("--wait", action="store_true", help="Poll list-contents until --expect items are ACTIVE first.")
    ap.add_argument("--expect", type=int, default=0, help="Expected content count for --wait (0 = any > 0).")
    ap.add_argument("--poll-seconds", type=int, default=20, help="Poll interval for --wait.")
    ap.add_argument("--max-wait", type=int, default=600, help="Max seconds to wait for ingestion.")
    args = ap.parse_args()

    manifest = _load_manifest(args.manifest)
    tags = _parse_tags(args.tags, manifest)

    # All AWS config (credentials, profile, region) comes from the environment
    # exactly as the AWS CLI / SDK resolve it — we never override the region or
    # build an explicit session, so the script always talks to the same
    # endpoint your shell does.
    # Resolve the KB id: explicit flag > manifest > SSM (the Phase 2 stack
    # publishes it to ssm_names.KB_ID), so a fresh deploy needs no hand-copying.
    kb_id = _resolve_kb_id(args.kb_id, manifest)
    print (f"KB:{kb_id}")
    if not kb_id:
        sys.exit(
            "No knowledge-base id: pass --kb-id, set knowledgeBaseId in the manifest, "
            f"or deploy Phase 2 so {ssm_names.KB_ID} exists in SSM."
        )

    qc = boto3.client("qconnect")

    print(f"KB:      {kb_id}")
    print(f"region:  {qc.meta.region_name}")
    print(f"tags:    {tags}")

    def list_active() -> list[dict]:
        items: list[dict] = []
        paginator = qc.get_paginator("list_contents")
        for page in paginator.paginate(knowledgeBaseId=kb_id):
            items.extend(page.get("contentSummaries", []))
        return items

    if args.wait:
        deadline = time.time() + args.max_wait
        while True:
            items = list_active()
            active = [c for c in items if c.get("status") == "ACTIVE"]
            print(f"  ingested: {len(active)}/{len(items)} ACTIVE")
            if active and (args.expect == 0 or len(active) >= args.expect):
                break
            if time.time() > deadline:
                sys.exit(f"Timed out waiting for ingestion (max-wait={args.max_wait}s).")
            time.sleep(args.poll_seconds)

    items = list_active()
    if not items:
        sys.exit("No content items found. Has the KB finished its first sync? Try --wait.")

    languages = [s.strip() for s in args.languages.split(",") if s.strip()]
    by_language: dict[str, int] = {}
    untagged_language: list[str] = []

    tagged = 0
    for c in items:
        arn = c["contentArn"]
        item_tags = dict(tags)
        if not args.no_language:
            lang = _detect_language(c, languages)
            if lang:
                item_tags[args.language_key] = lang
                by_language[lang] = by_language.get(lang, 0) + 1
            else:
                untagged_language.append(c.get("name", c["contentId"]))
        qc.tag_resource(resourceArn=arn, tags=item_tags)
        tagged += 1
        lang_note = f" [{args.language_key}={item_tags[args.language_key]}]" if args.language_key in item_tags else ""
        print(f"  tagged {c.get('name', c['contentId'])}{lang_note}")

    # Verify a sample.
    sample = qc.list_tags_for_resource(resourceArn=items[0]["contentArn"]).get("tags", {})
    print(f"\nTagged {tagged} content item(s). Sample tags now: {sample}")
    if not args.no_language:
        print(f"By {args.language_key}: " + (", ".join(f"{k}={v}" for k, v in sorted(by_language.items())) or "none detected"))
        if untagged_language:
            print(
                f"WARNING: no language path segment for {len(untagged_language)} item(s) "
                f"(left without a {args.language_key} tag): {', '.join(untagged_language[:10])}"
                + (" ..." if len(untagged_language) > 10 else "")
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
