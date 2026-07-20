"""
cdk_constructs/connect/lambda_integration.py — associate a Lambda function with an Amazon
Connect instance so contact flows can invoke it.

Unlike the MCP server (an APPLICATION integration wired via custom resources in
connect/mcp_integration.py), a Lambda association is a first-class CDK resource:
`connect.CfnIntegrationAssociation` natively accepts IntegrationType
LEX_BOT | LAMBDA_FUNCTION. Associating a Lambda this way is the standard
"Add Lambda function" step — it lets the "Invoke AWS Lambda function" flow block
call the function AND adds the resource-based policy that grants the Connect
service principal `lambda:InvokeFunction` on it.

The instance is identified by its ARN (the CfnIntegrationAssociation
`instance_id` prop takes the instance ARN), matching the rest of the stack
(flows, security profiles) which build the ARN from config.INSTANCE_ID.
"""

from __future__ import annotations

from aws_cdk import aws_connect as connect
from aws_cdk import aws_lambda as aws_lambda
from constructs import Construct


class LambdaConnectIntegration(Construct):
    """Associates a Lambda function with a Connect instance (LAMBDA_FUNCTION)."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        instance_arn: str,
        function: aws_lambda.IFunction,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.association = connect.CfnIntegrationAssociation(
            self,
            "Resource",
            instance_id=instance_arn,
            integration_type="LAMBDA_FUNCTION",
            integration_arn=function.function_arn,
        )

    @property
    def integration_association_id(self) -> str:
        return self.association.attr_integration_association_id
