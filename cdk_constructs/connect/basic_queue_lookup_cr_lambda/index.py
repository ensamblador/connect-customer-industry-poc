"""
basic_queue_lookup_cr_lambda/index.py — resolve a Connect queue ARN by name.

A CloudFormation custom-resource handler (driven by the cr.Provider framework)
that looks up a standard queue by NAME on a Connect instance and returns its
ARN + id. Queue ids are unique per instance, so a flow authored against one
instance can't carry another instance's literal queue ARN; this lookup lets the
contact-flows stack resolve the instance's BasicQueue at DEPLOY time.

Only ListQueues is called (paginated). On Delete it is a no-op. If no STANDARD
queue with the requested name exists, it raises so the deploy fails loudly
rather than wiring a bad queue id into the flow.
"""

from __future__ import annotations

import boto3

_connect = boto3.client("connect")


def handler(event, context):
    request_type = event["RequestType"]
    props = event.get("ResourceProperties", {})
    instance_id = props["InstanceId"]
    queue_name = props.get("QueueName", "BasicQueue")

    if request_type == "Delete":
        # Nothing to delete — this resource only reads.
        return {"PhysicalResourceId": event.get("PhysicalResourceId", "basic-queue-lookup")}

    arn = None
    queue_id = None
    paginator = _connect.get_paginator("list_queues")
    for page in paginator.paginate(InstanceId=instance_id, QueueTypes=["STANDARD"]):
        for q in page.get("QueueSummaryList", []):
            if q.get("Name") == queue_name:
                arn = q["Arn"]
                queue_id = q["Id"]
                break
        if arn:
            break

    if not arn:
        raise Exception(
            f"No STANDARD queue named {queue_name!r} found on instance {instance_id}."
        )

    return {
        "PhysicalResourceId": queue_id,
        "Data": {"QueueArn": arn, "QueueId": queue_id},
    }
