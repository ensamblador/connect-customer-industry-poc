"""
connect/security_profile.py — Amazon Connect security profile for an AI agent.

A Connect AI agent's tool access is governed by a security profile: each tool
the agent invokes maps to a human-agent permission that must be present on the
profile assigned to the agent. From the admin guide
(Assigning security profile permissions to AI agents):

    AI Agent Tool          -> Required permission (API name)
    ---------------------------------------------------------
    Knowledge Base (Retrieve)  Connect assistant - View Access  -> Wisdom.View
    Cases (Create/Update/Search) Cases - View/Edit              -> Cases.*
    Customer Profiles          Customer Profiles - View         -> CustomerProfiles.View
    Tasks (StartTaskContact)   Tasks - Create                   -> Tasks.Create

The banking self-service agent's only data tool is the KB **Retrieve** tool, so
the least-privilege profile carries a single permission: **`Wisdom.View`**.
This mirrors the existing `banco-selfservice-ai-agent` profile on the instance
(its sole permission is `Wisdom.View`).

`AiAgentSecurityProfile` wraps `connect.CfnSecurityProfile`. Pass `permissions`
to grant additional tool permissions (e.g. `Cases.View`, `CustomerProfiles.View`)
when the agent gains more tools; it defaults to `["Wisdom.View"]`.
"""

from __future__ import annotations

from aws_cdk import Fn, Stack
from aws_cdk import aws_connect as connect
from aws_cdk import aws_iam as iam
from aws_cdk import custom_resources as cr
from constructs import Construct

# Default least-privilege permission set: just the KB Retrieve tool.
DEFAULT_AI_AGENT_PERMISSIONS = ["Wisdom.View"]


class AiAgentSecurityProfile(Construct):
    """A least-privilege Connect security profile for an AI agent's tools."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        instance_id: str,
        name: str,
        permissions: list[str] | None = None,
        mcp_applications: dict[str, list[str]] | None = None,
        description: str = "",
        tags: dict[str, str] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Keep the bare instance id for the assignment SDK calls (which take
        # the id, unlike CfnSecurityProfile which needs the full ARN).
        stack = Stack.of(self)
        if instance_id.startswith("arn:"):
            instance_arn = instance_id
            self._instance_id = instance_id.split("/")[-1]
        else:
            self._instance_id = instance_id
            instance_arn = (
                f"arn:aws:connect:{stack.region}:{stack.account}:instance/{instance_id}"
            )

        # MCP tool access is granted via the `applications` block, NOT flat
        # permissions: one entry per MCP namespace, Type=MCP, with
        # ApplicationPermissions = the per-tool identifiers (max 10 per app).
        # mcp_applications maps namespace -> [tool identifiers].
        applications = [
            connect.CfnSecurityProfile.ApplicationProperty(
                namespace=ns,
                type="MCP",
                application_permissions=tool_ids,
            )
            for ns, tool_ids in (mcp_applications or {}).items()
        ]

        self.security_profile = connect.CfnSecurityProfile(
            self,
            "Resource",
            instance_arn=instance_arn,
            security_profile_name=name,
            permissions=permissions or list(DEFAULT_AI_AGENT_PERMISSIONS),
            applications=applications or None,
            description=description
            or f"Least-privilege profile for the {name} AI agent.",
            tags=[{"key": k, "value": v} for k, v in (tags or {}).items()] or None,
        )

    # ------------------------------------------------------------------ #
    def assign_to_ai_agent(
        self,
        ai_agent_arn: str,
        id_suffix: str = "",
        depends_on: Construct | None = None,
    ) -> list[cr.AwsCustomResource]:
        """
        Assign this security profile to an AI agent via the Connect
        Associate/DisassociateSecurityProfiles APIs (no CloudFormation
        property expresses this binding, so it's an SDK custom resource —
        same pattern as the MCP integration).

        Associates the BASE (unqualified) agent ARN, which Connect resolves to
        ``:$LATEST`` — the version the runtime uses.

        The editable console **draft** (``:$SAVED``) is NOT associated here.
        It cannot be done through this ``AwsCustomResource`` path: the
        association lands through the **JS AWS SDK**, whose internal
        ``GetAiAgent`` validation rejects a ``:$SAVED`` (or numeric
        ``:<version>``) qualified ARN with "Invalid parameters for GetAiAgent"
        — even though the byte-identical ARN succeeds through the CLI /
        botocore path. So the draft binding must be done either:

          * out-of-band after deploy with the CLI (botocore), e.g.::

                aws connect associate-security-profiles --instance-id <id> \\
                  --security-profiles Id=<profileId> --entity-type AI_AGENT \\
                  --entity-arn <agentArn>:'$SAVED'

          * or via a boto3-backed Lambda custom resource (matches the working
            botocore path), rather than this JS-SDK ``AwsCustomResource``.

        ``depends_on`` (the agent's ``CfnAIAgentVersion``) is accepted for
        ordering but does not change the JS-SDK ``$SAVED`` limitation.

        Pass a unique ``id_suffix`` per agent ("Voice", "Chat") so the
        per-assignment child constructs don't collide on logical id.
        """
        profile_id = Fn.select(
            1, Fn.split("/security-profile/", self.security_profile_arn)
        )

        entity_arns: dict[str, str] = {
            "Base": ai_agent_arn,
        }

        if not hasattr(self, "assignments"):
            self.assignments = {}
        created: list[cr.AwsCustomResource] = []

        for qualifier, entity_arn in entity_arns.items():
            params = {
                "InstanceId": self._instance_id,
                "SecurityProfiles": [{"Id": profile_id}],
                "EntityType": "AI_AGENT",
                "EntityArn": entity_arn,
            }
            assignment = cr.AwsCustomResource(
                self,
                f"Assignment{id_suffix}{qualifier}",
                install_latest_aws_sdk=True,  # AI_AGENT entity type is new
                on_create=cr.AwsSdkCall(
                    service="connect",
                    action="associateSecurityProfiles",
                    parameters=params,
                    physical_resource_id=cr.PhysicalResourceId.of(
                        f"{self.security_profile_id}:{entity_arn}"
                    ),
                ),
                on_update=cr.AwsSdkCall(
                    service="connect",
                    action="associateSecurityProfiles",
                    parameters=params,
                    physical_resource_id=cr.PhysicalResourceId.of(
                        f"{self.security_profile_id}:{entity_arn}"
                    ),
                ),
                on_delete=cr.AwsSdkCall(
                    service="connect",
                    action="disassociateSecurityProfiles",
                    parameters=params,
                ),
                policy=cr.AwsCustomResourcePolicy.from_statements(
                    [
                        iam.PolicyStatement(
                            actions=[
                                "connect:AssociateSecurityProfiles",
                                "connect:DisassociateSecurityProfiles",
                            ],
                            resources=["*"],
                        ),
                        # AssociateSecurityProfiles validates the AI agent ARN
                        # against Wisdom, so the caller needs to read the agent.
                        iam.PolicyStatement(
                            actions=["wisdom:GetAIAgent"],
                            resources=["*"],
                        ),
                    ]
                ),
            )
            # The profile must exist before it can be assigned.
            assignment.node.add_dependency(self.security_profile)
            # And (for $SAVED) the agent's published version must exist first,
            # so the draft is resolvable by GetAiAgent.
            if depends_on is not None:
                assignment.node.add_dependency(depends_on)
            self.assignments[f"{id_suffix or 'default'}-{qualifier}"] = assignment
            created.append(assignment)
        return created

    @property
    def security_profile_arn(self) -> str:
        return self.security_profile.attr_security_profile_arn

    @property
    def security_profile_id(self) -> str:
        # CfnSecurityProfile exposes only the ARN (Ref == ARN), so derive the
        # bare GUID from ".../security-profile/<id>". This is what the SSM bus
        # publishes and what connect:AssociateSecurityProfiles expects.
        return Fn.select(1, Fn.split("/security-profile/", self.security_profile_arn))
