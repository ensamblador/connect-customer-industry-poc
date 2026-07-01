"""
connect/prompt_lookup_cr.py — resolve an Amazon Connect prompt id/ARN by NAME
at deploy time via a CDK custom resource.

Prompt ids differ per instance, so hard-coding one is not portable. This
construct takes a stable prompt NAME (e.g. "Music_Rock_EverywhereTheSunShines_
Inst.wav"), and at deploy time its Lambda paginates ``connect:ListPrompts`` for
the instance until it finds the prompt with that name, returning the resolved
``PromptId`` and ``PromptArn``. Synthesis performs no AWS call — the lookup runs
only when CloudFormation invokes the custom resource at deploy.

Implementation note — DIRECT Lambda-backed custom resource (no ``cr.Provider``):
the lookup is a single, fast, synchronous call, so it does not need the
``cr.Provider`` framework (which exists for long-running/async resources and
adds a second "framework" Lambda + role + policy + log group). Instead the
``CustomResource``'s ``ServiceToken`` is the handler Lambda's ARN directly, and
the handler speaks the CloudFormation custom-resource response protocol itself
(see ``prompt_lookup_lambda/index.py``). CloudFormation can invoke a Lambda
custom resource in the same account/region without an explicit
``AWS::Lambda::Permission``, so none is added.

Usage:
    music = PromptByName(
        self, "QueueMusicPrompt",
        instance_id=config.INSTANCE_ID,
        prompt_name="Music_Rock_EverywhereTheSunShines_Inst.wav",
    )
    music.prompt_id / music.prompt_arn
"""

from __future__ import annotations

import os

from aws_cdk import CustomResource, Duration, Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from constructs import Construct

_LAMBDA_DIR = os.path.join(os.path.dirname(__file__), "prompt_lookup_lambda")


class _PromptLookupProvider(Construct):
    """Singleton (per stack) Lambda that resolves a prompt by name.

    Holds only the handler Lambda; its ARN is used directly as the
    ``CustomResource`` service token (no ``cr.Provider`` framework Lambda).
    """

    PROVIDER_ID = "PromptLookupProvider"

    @classmethod
    def get_or_create(cls, scope: Construct) -> "_PromptLookupProvider":
        stack = Stack.of(scope)
        existing = stack.node.try_find_child(cls.PROVIDER_ID)
        if existing is not None:
            return existing  # type: ignore[return-value]
        return cls(stack, cls.PROVIDER_ID)

    def __init__(self, scope: Construct, construct_id: str) -> None:
        super().__init__(scope, construct_id)

        self.on_event = _lambda.Function(
            self,
            "OnEvent",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="index.handler",
            code=_lambda.Code.from_asset(_LAMBDA_DIR),
            timeout=Duration.minutes(2),
            description="Resolves an Amazon Connect prompt id/ARN by name via "
            "ListPrompts (deploy-time lookup; ids are instance-specific). "
            "Sends its own CloudFormation custom-resource response.",
        )
        # ListPrompts is not resource-scopable in a useful way; scope to the
        # action on all resources (a read-only describe-style call).
        self.on_event.add_to_role_policy(
            iam.PolicyStatement(
                actions=["connect:ListPrompts"],
                resources=["*"],
            )
        )

    @property
    def service_token(self) -> str:
        # The handler Lambda's ARN is the custom resource service token: CFN
        # invokes the handler directly (no provider framework in between).
        return self.on_event.function_arn


class PromptByName(Construct):
    """Resolves one Connect prompt's id/ARN by name (deploy-time custom resource)."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        instance_id: str,
        prompt_name: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        provider = _PromptLookupProvider.get_or_create(self)

        self.resource = CustomResource(
            self,
            "Resource",
            service_token=provider.service_token,
            resource_type="Custom::ConnectPromptByName",
            properties={
                "InstanceId": instance_id,
                "PromptName": prompt_name,
            },
        )

    @property
    def prompt_id(self) -> str:
        return self.resource.get_att_string("PromptId")

    @property
    def prompt_arn(self) -> str:
        return self.resource.get_att_string("PromptArn")
