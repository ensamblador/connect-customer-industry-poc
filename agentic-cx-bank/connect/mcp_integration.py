"""
connect/mcp_integration.py — register an AgentCore MCP gateway as an Amazon
Connect instance integration.

This is NOT a Lex/Lambda IntegrationAssociation. `connect.CfnIntegrationAssociation`
only accepts LEX_BOT | LAMBDA_FUNCTION, so the MCP server is wired as a
THIRD-PARTY APPLICATION, in two steps (both via custom resources — there is no
native CDK construct for an AppIntegrations MCP_SERVER application):

  1. AppIntegrations CreateApplication with ApplicationType=MCP_SERVER:
       * AccessUrl  = the gateway's MCP URL (.../mcp)
       * Namespace  = the gateway ID EXACTLY (verified requirement — any other
                      value fails "Namespace for MCP server applications must
                      be a valid Bedrock Agent Core Gateway ID")
     -> returns the application ARN.
  2. Connect CreateIntegrationAssociation with IntegrationType=APPLICATION and
     IntegrationArn = that application ARN -> associates it to the instance.

Prereq (enforced by Connect, not here): the instance must be configured with
the gateway's Discovery URL, and a gateway maps to exactly one instance / one
MCP server.

The `Application` API is in preview; shapes may change.
"""

from __future__ import annotations

from aws_cdk import CustomResource, Duration, Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import custom_resources as cr
from constructs import Construct

# On delete, Connect refuses to DeleteIntegrationAssociation while ANY security
# profile still grants MCP access to this application ("The application is being
# used in a security profile."). Those grants live on the Phase 3 AI-agent
# security profiles and reference the app only by namespace string (= gateway
# id), so there is no CloudFormation dependency that tears them down first.
# This handler strips this app's namespace from every security profile that
# carries it, so the association delete can proceed automatically.
_DETACH_HANDLER_SRC = '''
import boto3

connect = boto3.client("connect")


def _profile_ids(instance_id):
    token = None
    while True:
        kw = {"InstanceId": instance_id, "MaxResults": 100}
        if token:
            kw["NextToken"] = token
        resp = connect.list_security_profiles(**kw)
        for s in resp.get("SecurityProfileSummaryList", []):
            yield s["Id"]
        token = resp.get("NextToken")
        if not token:
            break


def on_event(event, context):
    pid = event.get("PhysicalResourceId", "mcp-sp-detacher")
    if event.get("RequestType") != "Delete":
        return {"PhysicalResourceId": pid}

    props = event["ResourceProperties"]
    instance_id = props["InstanceId"]
    namespace = props["Namespace"]

    for sp_id in _profile_ids(instance_id):
        apps = connect.list_security_profile_applications(
            InstanceId=instance_id, SecurityProfileId=sp_id
        ).get("Applications", [])
        if any(a.get("Namespace") == namespace for a in apps):
            remaining = [
                {
                    "Namespace": a["Namespace"],
                    "ApplicationPermissions": a.get("ApplicationPermissions", []),
                }
                for a in apps
                if a.get("Namespace") != namespace
            ]
            connect.update_security_profile(
                InstanceId=instance_id,
                SecurityProfileId=sp_id,
                Applications=remaining,
            )

    return {"PhysicalResourceId": pid}
'''


class McpServerIntegration(Construct):
    """Registers an AgentCore MCP gateway as a Connect APPLICATION integration."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        instance_id: str,
        gateway_id: str,
        gateway_mcp_url: str,
        application_name: str,
        description: str = "",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ---- Step 1: AppIntegrations MCP_SERVER application ---------------
        create_app_params = {
            "Name": application_name,
            # Namespace MUST be the gateway id (verified requirement).
            "Namespace": gateway_id,
            "ApplicationType": "MCP_SERVER",
            "ApplicationSourceConfig": {
                "ExternalUrlConfig": {"AccessUrl": gateway_mcp_url}
            },
        }
        if description:
            create_app_params["Description"] = description

        self.application = cr.AwsCustomResource(
            self,
            "Application",
            install_latest_aws_sdk=True,  # MCP_SERVER type is new in the SDK
            on_create=cr.AwsSdkCall(
                service="appintegrations",
                action="createApplication",
                parameters=create_app_params,
                # Physical id = the application ARN, because DeleteApplication
                # takes the ARN (so PhysicalResourceIdReference resolves to it).
                physical_resource_id=cr.PhysicalResourceId.from_response("Arn"),
            ),
            # AppIntegrations applications are immutable in the fields we set;
            # recreate on change by keying the physical id to namespace+url.
            on_update=cr.AwsSdkCall(
                service="appintegrations",
                action="createApplication",
                parameters=create_app_params,
                physical_resource_id=cr.PhysicalResourceId.from_response("Arn"),
            ),
            on_delete=cr.AwsSdkCall(
                service="appintegrations",
                action="deleteApplication",
                # DeleteApplication takes the application ARN (the physical id).
                parameters={"Arn": cr.PhysicalResourceIdReference()},
                # If CreateApplication failed, the physical id was never set to
                # a real ARN (CFN falls back to a log-stream-like value), so the
                # rollback DeleteApplication would fail the ARN regex with a
                # ValidationException and wedge the stack in
                # UPDATE_ROLLBACK_FAILED. Tolerate that (and a missing app) so a
                # failed create rolls back cleanly instead of getting stuck.
                ignore_error_codes_matching="ValidationException|ResourceNotFoundException",
            ),
            policy=cr.AwsCustomResourcePolicy.from_statements(
                [
                    iam.PolicyStatement(
                        actions=[
                            "app-integrations:CreateApplication",
                            "app-integrations:DeleteApplication",
                            "app-integrations:GetApplication",
                            "app-integrations:TagResource",
                        ],
                        resources=["*"],
                    ),
                    # CreateApplication for an MCP_SERVER validates the
                    # namespace (= gateway id) against the real gateway, so the
                    # role must be allowed to read it ("Missing permissions to
                    # access gateway" otherwise).
                    iam.PolicyStatement(
                        actions=[
                            "bedrock-agentcore:GetGateway",
                            "bedrock-agentcore:ListGateways",
                        ],
                        resources=["*"],
                    ),
                ]
            ),
        )
        self.application_arn = self.application.get_response_field("Arn")

        # ---- Step 2: associate the application to the Connect instance ----
        self.association = cr.AwsCustomResource(
            self,
            "Association",
            install_latest_aws_sdk=True,
            on_create=cr.AwsSdkCall(
                service="connect",
                action="createIntegrationAssociation",
                parameters={
                    "InstanceId": instance_id,
                    "IntegrationType": "APPLICATION",
                    "IntegrationArn": self.application_arn,
                },
                physical_resource_id=cr.PhysicalResourceId.from_response(
                    "IntegrationAssociationId"
                ),
            ),
            on_delete=cr.AwsSdkCall(
                service="connect",
                action="deleteIntegrationAssociation",
                parameters={
                    "InstanceId": instance_id,
                    "IntegrationAssociationId": cr.PhysicalResourceIdReference(),
                },
            ),
            policy=cr.AwsCustomResourcePolicy.from_statements(
                [
                    iam.PolicyStatement(
                        actions=[
                            "connect:CreateIntegrationAssociation",
                            "connect:DeleteIntegrationAssociation",
                            "app-integrations:GetApplication",
                            # Connect's CreateIntegrationAssociation internally
                            # creates an application association on the
                            # AppIntegrations app, so the caller needs these.
                            "app-integrations:CreateApplicationAssociation",
                            "app-integrations:DeleteApplicationAssociation",
                            "app-integrations:ListApplicationAssociations",
                        ],
                        resources=["*"],
                    ),
                    # Associating an APPLICATION integration makes Connect
                    # update its service-linked role ("Access denied updating
                    # the Amazon Connect service-linked role" otherwise), so
                    # the caller needs SLR create + policy-attach permissions.
                    iam.PolicyStatement(
                        actions=[
                            "iam:CreateServiceLinkedRole",
                            "iam:PutRolePolicy",
                            "iam:AttachRolePolicy",
                            "iam:GetRole",
                        ],
                        resources=[
                            "arn:aws:iam::*:role/aws-service-role/connect.amazonaws.com/*"
                        ],
                    ),
                ]
            ),
        )
        # Associate only after the application exists.
        self.association.node.add_dependency(self.application)

        # ---- Step 3: security-profile grant detacher (delete-time only) ---
        # Connect blocks DeleteIntegrationAssociation while any security profile
        # still grants MCP access to this application's namespace. On teardown,
        # strip that grant from every referencing profile FIRST, so the
        # association (and then the application) delete cleanly without manual
        # console/CLI intervention. No-op on create/update.
        stack = Stack.of(self)
        instance_arn = (
            f"arn:aws:connect:{stack.region}:{stack.account}:instance/{instance_id}"
        )
        detach_fn = _lambda.Function(
            self,
            "ProfileDetacherFn",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="index.on_event",
            code=_lambda.Code.from_inline(_DETACH_HANDLER_SRC),
            timeout=Duration.minutes(5),
        )
        detach_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "connect:ListSecurityProfiles",
                    "connect:ListSecurityProfileApplications",
                    "connect:UpdateSecurityProfile",
                ],
                resources=[instance_arn, f"{instance_arn}/*"],
            )
        )
        detach_provider = cr.Provider(
            self,
            "ProfileDetacherProvider",
            on_event_handler=detach_fn,
        )
        self.profile_detacher = CustomResource(
            self,
            "ProfileDetacher",
            service_token=detach_provider.service_token,
            properties={
                "InstanceId": instance_id,
                # The security-profile MCP grant namespace == the gateway id ==
                # this application's Namespace.
                "Namespace": gateway_id,
            },
        )
        # Deleted BEFORE the association (add_dependency => this is torn down
        # first), so the grants are gone before DeleteIntegrationAssociation.
        self.profile_detacher.node.add_dependency(self.association)

    @property
    def integration_association_id(self) -> str:
        return self.association.get_response_field("IntegrationAssociationId")
