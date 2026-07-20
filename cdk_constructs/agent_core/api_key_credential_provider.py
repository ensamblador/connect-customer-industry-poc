"""
cdk_constructs/agent_core/api_key_credential_provider.py — AgentCore API Key credential
provider, created via a custom resource.

OpenAPI-schema gateway targets require an explicit credential provider (the
deploy failed with "IamCredentialProvider is required for openApiSchema
targets..."). For API-key auth the provider is an AgentCore *API Key
credential provider*, which AgentCore stores in its Token Vault and exposes by
ARN. There is no L1/L2 construct for it, so we create it with an
AwsCustomResource calling bedrock-agentcore-control:CreateApiKeyCredentialProvider
(and DeleteApiKeyCredentialProvider on teardown).

Source of truth for the key value
----------------------------------
A Secrets Manager secret holds the API key. The SAME secret feeds:
  * the API Gateway ApiKey value (so the backend accepts the key), and
  * this credential provider (apiKeySecretSource=EXTERNAL → the secret),
so AgentCore sends exactly the key the API expects. The plaintext key never
appears in the CDK code or the template (only the secret ARN does).
"""

from __future__ import annotations

from aws_cdk import aws_iam as iam
from aws_cdk import aws_secretsmanager as sm
from aws_cdk import custom_resources as cr
from constructs import Construct


class ApiKeyCredentialProvider(Construct):
    """Creates an AgentCore API Key credential provider from a secret."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        provider_name: str,
        secret: sm.ISecret,
        secret_json_key: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        create_params = {
            "name": provider_name,
            "apiKeySecretSource": "EXTERNAL",
            "apiKeySecretConfig": {
                "secretId": secret.secret_arn,
                "jsonKey": secret_json_key,
            },
        }

        self.resource = cr.AwsCustomResource(
            self,
            "Resource",
            # The default Lambda runtime SDK is too old to know the
            # apiKeySecretSource / apiKeySecretConfig parameters and silently
            # drops them (the service then sees source=MANAGED and demands a
            # raw apiKey). Force the latest SDK so EXTERNAL is honored.
            install_latest_aws_sdk=True,
            on_create=cr.AwsSdkCall(
                service="bedrock-agentcore-control",
                action="createApiKeyCredentialProvider",
                parameters=create_params,
                # The provider ARN is the value downstream needs; surface it
                # as the physical id so it's available via get_response_field.
                physical_resource_id=cr.PhysicalResourceId.from_response(
                    "credentialProviderArn"
                ),
            ),
            on_update=cr.AwsSdkCall(
                service="bedrock-agentcore-control",
                action="createApiKeyCredentialProvider",
                parameters=create_params,
                physical_resource_id=cr.PhysicalResourceId.from_response(
                    "credentialProviderArn"
                ),
            ),
            on_delete=cr.AwsSdkCall(
                service="bedrock-agentcore-control",
                action="deleteApiKeyCredentialProvider",
                parameters={"name": provider_name},
            ),
            policy=cr.AwsCustomResourcePolicy.from_statements(
                [
                    iam.PolicyStatement(
                        actions=[
                            "bedrock-agentcore:CreateApiKeyCredentialProvider",
                            "bedrock-agentcore:DeleteApiKeyCredentialProvider",
                            "bedrock-agentcore:GetApiKeyCredentialProvider",
                            # Creating the first credential provider lazily
                            # provisions the account's default Token Vault, so
                            # the caller needs the token-vault actions too.
                            "bedrock-agentcore:CreateTokenVault",
                            "bedrock-agentcore:GetTokenVault",
                        ],
                        resources=["*"],
                    ),
                    iam.PolicyStatement(
                        actions=["secretsmanager:GetSecretValue"],
                        resources=[secret.secret_arn],
                    ),
                    # AgentCore stores the API key in a Secrets Manager secret
                    # inside the Token Vault and may use a KMS key to encrypt
                    # it; allow the create/tag/describe it performs on first use.
                    iam.PolicyStatement(
                        actions=[
                            "secretsmanager:CreateSecret",
                            "secretsmanager:TagResource",
                            "secretsmanager:DescribeSecret",
                            "secretsmanager:PutSecretValue",
                        ],
                        resources=["*"],
                    ),
                    iam.PolicyStatement(
                        actions=[
                            "kms:CreateKey",
                            "kms:Decrypt",
                            "kms:GenerateDataKey",
                        ],
                        resources=["*"],
                    ),
                ]
            ),
        )
        self.resource.node.add_dependency(secret)

    @property
    def credential_provider_arn(self) -> str:
        """ARN of the created API Key credential provider."""
        return self.resource.get_response_field("credentialProviderArn")
