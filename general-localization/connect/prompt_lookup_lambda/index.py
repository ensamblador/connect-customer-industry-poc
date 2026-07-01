"""
Custom-resource handler that resolves an Amazon Connect prompt id/ARN by NAME.

Prompt ids are instance-specific, so the flow references the prompt by a stable
name and this handler resolves the id at deploy time. It paginates
``connect:list_prompts`` for the instance and returns the prompt whose ``Name``
matches exactly. If no prompt matches (or the lookup errors / returns nothing),
it falls back to the FIRST prompt in the list rather than raising, so a naming
mismatch never blocks the CloudFormation stack.

DIRECT Lambda-backed custom resource: there is no ``cr.Provider`` framework
Lambda in front of this handler, so the handler MUST speak the CloudFormation
custom-resource response protocol itself — it PUTs a SUCCESS/FAILED result to
the pre-signed ``event["ResponseURL"]`` (via the stdlib ``urllib.request``, no
extra dependency). It always sends a response — including on an unexpected
exception — so CloudFormation never hangs until timeout.

Contract (driven by the PromptByName CDK construct):
  ResourceProperties:
    InstanceId  - the Amazon Connect instance id
    PromptName  - the exact prompt name to resolve (e.g. a system prompt
                  like "Music_Rock_EverywhereTheSunShines_Inst.wav")
  Returns Data: PromptId, PromptArn
"""

import json
import urllib.request

import boto3

connect = boto3.client("connect")

SUCCESS = "SUCCESS"
FAILED = "FAILED"


def _send_response(event, context, status, data, physical_resource_id, reason=None):
    """PUT the custom-resource result to the CloudFormation pre-signed URL.

    Implements the CloudFormation custom-resource response protocol that the
    ``cr.Provider`` framework would otherwise handle. Uses the stdlib
    ``urllib.request`` so the handler needs no dependency beyond boto3.
    """
    log_stream = getattr(context, "log_stream_name", "")
    body = {
        "Status": status,
        "Reason": reason or f"See CloudWatch log stream: {log_stream}",
        # A stable, non-empty physical id is required; fall back to the log
        # stream name when the lookup produced none.
        "PhysicalResourceId": physical_resource_id or log_stream or "prompt-lookup",
        "StackId": event["StackId"],
        "RequestId": event["RequestId"],
        "LogicalResourceId": event["LogicalResourceId"],
        "NoEcho": False,
        "Data": data or {},
    }
    encoded = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        event["ResponseURL"],
        data=encoded,
        method="PUT",
        # CloudFormation requires an empty content-type and the byte length.
        headers={"content-type": "", "content-length": str(len(encoded))},
    )
    # The URL is a CloudFormation-issued pre-signed S3 URL.
    urllib.request.urlopen(request)  # noqa: S310


def _list_prompts(instance_id):
    """Return all prompt summaries for the instance (best-effort, never raises)."""
    prompts = []
    try:
        paginator = connect.get_paginator("list_prompts")
        for page in paginator.paginate(InstanceId=instance_id):
            prompts.extend(page.get("PromptSummaryList", []))
    except Exception as exc:  # never fail the stack on a lookup error
        print(f"ListPrompts error (ignored): {exc}")
    return prompts


def _resolve(event):
    """Resolve the prompt and return ``(physical_resource_id, data)``.

    Prefers an exact name match; otherwise falls back to the FIRST prompt so a
    naming mismatch (or an empty/failed lookup) never fails the stack.
    """
    p = event["ResourceProperties"]
    instance_id = p["InstanceId"]
    prompt_name = p["PromptName"]

    prompts = _list_prompts(instance_id)
    chosen = next((pr for pr in prompts if pr.get("Name") == prompt_name), None)
    if chosen is None:
        if prompts:
            chosen = prompts[0]
            print(
                f"Prompt {prompt_name!r} not found in instance {instance_id}; "
                f"falling back to first prompt {chosen.get('Name')!r}."
            )
        else:
            # Nothing to return — still succeed so the stack is not blocked.
            print(
                f"No prompts found in instance {instance_id}; returning empty "
                "prompt id (stack not blocked)."
            )
            return "no-prompt", {"PromptId": "", "PromptArn": ""}

    return chosen["Id"], {"PromptId": chosen["Id"], "PromptArn": chosen["Arn"]}


def handler(event, context):
    rt = event.get("RequestType")
    print(f"RequestType={rt} props={event.get('ResourceProperties', {})}")
    try:
        if rt in ("Create", "Update"):
            physical_id, data = _resolve(event)
            _send_response(event, context, SUCCESS, data, physical_id)
        elif rt == "Delete":
            # Read-only lookup — nothing to delete; echo the existing id.
            _send_response(
                event,
                context,
                SUCCESS,
                {},
                event.get("PhysicalResourceId", ""),
            )
        else:
            _send_response(
                event,
                context,
                FAILED,
                {},
                event.get("PhysicalResourceId", ""),
                reason=f"Unknown request type: {rt}",
            )
    except Exception as exc:
        # Always respond so CloudFormation does not hang until timeout.
        print(f"handler error: {exc}")
        _send_response(
            event,
            context,
            FAILED,
            {},
            event.get("PhysicalResourceId", ""),
            reason=f"Handler exception: {exc}",
        )
