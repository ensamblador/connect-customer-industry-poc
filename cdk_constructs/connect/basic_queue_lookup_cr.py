"""
connect/basic_queue_lookup_cr.py — resolve a Connect queue ARN by name at deploy
time via a boto3 custom resource.

Root cause this works around: Connect queue ids are unique PER INSTANCE, so a
contact flow / flow module authored against one instance cannot carry another
instance's literal queue ARN (Connect rejects it: "Failed to convert id"). There
is no CloudFormation way to look a queue up by name. This construct wires a tiny
``connect:ListQueues`` Lambda (driven by the cr.Provider framework) that returns
the instance's queue ARN for a given name (default ``BasicQueue``), so the flow
JSON's ``BASIC_QUEUE_ARN_PLACEHOLDER`` resolves at DEPLOY time against whatever
instance is being deployed to.

Usage:
    q = BasicQueueLookup(self, "BasicQueueLookup", instance_id=config.INSTANCE_ID)
    replacements={"BASIC_QUEUE_ARN_PLACEHOLDER": q.queue_arn}
"""

from __future__ import annotations

import os

from aws_cdk import CustomResource, Duration, Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_logs as logs
from aws_cdk import custom_resources as cr
from constructs import Construct

_LAMBDA_DIR = os.path.join(os.path.dirname(__file__), "basic_queue_lookup_cr_lambda")


class BasicQueueLookup(Construct):
    """Look up a Connect standard-queue ARN by name at deploy time."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        instance_id: str,
        queue_name: str = "BasicQueue",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        stack = Stack.of(self)

        on_event = _lambda.Function(
            self,
            "OnEvent",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="index.handler",
            code=_lambda.Code.from_asset(_LAMBDA_DIR),
            timeout=Duration.minutes(1),
            description="Resolves a Connect queue ARN by name at deploy time "
            "(queue ids are per-instance, so flow JSON can't hard-code them).",
        )
        on_event.add_to_role_policy(
            iam.PolicyStatement(
                actions=["connect:ListQueues"],
                resources=[
                    f"arn:aws:connect:{stack.region}:{stack.account}:instance/{instance_id}",
                    f"arn:aws:connect:{stack.region}:{stack.account}:instance/{instance_id}/queue/*",
                ],
            )
        )
        provider = cr.Provider(
            self,
            "Provider",
            on_event_handler=on_event,
            log_group=logs.LogGroup(
                self,
                "ProviderLogGroup",
                retention=logs.RetentionDays.ONE_WEEK,
            ),
        )
        self.resource = CustomResource(
            self,
            "Resource",
            service_token=provider.service_token,
            resource_type="Custom::ConnectBasicQueueLookup",
            properties={"InstanceId": instance_id, "QueueName": queue_name},
        )

    @property
    def queue_arn(self) -> str:
        return self.resource.get_att_string("QueueArn")

    @property
    def queue_id(self) -> str:
        return self.resource.get_att_string("QueueId")
