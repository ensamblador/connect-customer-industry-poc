"""
connect/ai_agent_logging.py — CloudWatch logging for the Q in Connect AI agents.

Connect AI agent logging is CloudWatch Logs *vended log delivery* off the
assistant (a.k.a. the AI Agents domain), NOT a per-agent setting. Three native
``AWS::Logs::*`` resources wire it up (admin guide: "Monitor AI agents using
CloudWatch"):

    DeliverySource (logType=EVENT_LOGS, resourceArn=<assistant arn>)
        -> DeliveryDestination (a CloudWatch log group)
            -> Delivery (links source to destination)

``EVENT_LOGS`` captures the full agent journey — orchestration messages, tool
use / tool results, LLM invocations, AI-agent traces (token usage, guardrail
assessments), and orchestration errors — keyed by ``session_id`` / ``session_name``.

The destination log group name uses the ``/aws/vendedlogs/`` prefix so CloudWatch
Logs auto-manages the resource policy that lets ``delivery.logs.amazonaws.com``
write to it (no manual CfnResourcePolicy needed).

Why this construct lives HERE (``general-localization``, not the industry
projects): the ``ASSISTANT_ID`` (the Q in Connect AI Agents domain) is SHARED
across every industry project (telco, bank, ...) on the account, and CloudWatch
Logs allows only ONE ``EVENT_LOGS`` delivery source per resource. Provisioning
this logging once, in the shared localization app, avoids the
``ConflictException`` a second industry stack hits when it tries to create its
own delivery source against the same assistant. Each industry project's
``AiAgentsStack`` therefore does NOT create any logging resource or custom
resource for this — see their READMEs for the manual cross-check.

Deployer note: the principal running the deploy needs
``wisdom:AllowVendedLogDeliveryForResource`` (plus the standard
``logs:Put*Delivery*`` / ``logs:CreateDelivery`` permissions) to create the
delivery against the assistant.
"""

from __future__ import annotations

from aws_cdk import RemovalPolicy
from aws_cdk import aws_logs as logs
from constructs import Construct

# Common retention-day values -> the CDK enum. Falls back to ONE_MONTH.
_RETENTION = {
    1: logs.RetentionDays.ONE_DAY,
    3: logs.RetentionDays.THREE_DAYS,
    5: logs.RetentionDays.FIVE_DAYS,
    7: logs.RetentionDays.ONE_WEEK,
    14: logs.RetentionDays.TWO_WEEKS,
    30: logs.RetentionDays.ONE_MONTH,
    60: logs.RetentionDays.TWO_MONTHS,
    90: logs.RetentionDays.THREE_MONTHS,
    180: logs.RetentionDays.SIX_MONTHS,
    365: logs.RetentionDays.ONE_YEAR,
}


class AiAgentLogging(Construct):
    """Delivers Q in Connect assistant EVENT_LOGS to a CloudWatch log group."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        assistant_arn: str,
        log_group_name: str,
        retention_days: int = 30,
        source_name: str = "connect-ai-agents-event-logs",
        removal_policy: RemovalPolicy = RemovalPolicy.DESTROY,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.log_group = logs.LogGroup(
            self,
            "LogGroup",
            log_group_name=log_group_name,
            retention=_RETENTION.get(retention_days, logs.RetentionDays.ONE_MONTH),
            removal_policy=removal_policy,
        )

        # Source: the assistant resource, EVENT_LOGS.
        self.source = logs.CfnDeliverySource(
            self,
            "Source",
            name=source_name,
            resource_arn=assistant_arn,
            log_type="EVENT_LOGS",
        )

        # Destination: the CloudWatch log group, JSON output.
        self.destination = logs.CfnDeliveryDestination(
            self,
            "Destination",
            name=f"{source_name}-cwl",
            destination_resource_arn=self.log_group.log_group_arn,
            output_format="json",
        )

        # Delivery: link source -> destination. delivery_source_name is a literal
        # (not a ref), so declare the dependency explicitly.
        self.delivery = logs.CfnDelivery(
            self,
            "Delivery",
            delivery_source_name=source_name,
            delivery_destination_arn=self.destination.attr_arn,
        )
        self.delivery.add_resource_dependency(self.source)
        self.delivery.add_resource_dependency(self.destination)
