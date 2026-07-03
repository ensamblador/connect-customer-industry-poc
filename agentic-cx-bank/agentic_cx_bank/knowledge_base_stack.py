"""
agentic_cx_bank/knowledge_base_stack.py — Phase 2: the Q in Connect knowledge base.

Builds one EXTERNAL Wisdom knowledge base from the repo's plain-text (.txt)
entries under
knowledge_bases/bank/entries/<lang>/ (es, pt, en — uploaded together under the
bank/ prefix), associates it with the Q in Connect AI Agents domain, and
publishes the two values later phases consume:

    KB_ID        — Phase 3 binds the activate-card guide content association to it
    KB_ASSOC_ID  — Phase 4 binds the agents' Retrieve tool to it

Reuses knowledge_bases/knowledge_base.py (S3KnowledgeBase) verbatim: KMS key ->
S3 bucket -> BucketDeployment of the entries -> AppIntegrations DataIntegration
-> EXTERNAL CfnKnowledgeBase, plus the assistant association.

Two operational notes:

  * AWS::Wisdom::KnowledgeBase has NO update path. To rebuild the KB (e.g. after
    changing the content source), tear this stack down and redeploy it:
        cdk destroy CX-BANCO-KB
        cdk deploy  CX-BANCO-KB
    Because KB_ASSOC_ID is republished on the bus, Phase 4 auto-rewires the
    agents' Retrieve tool to the new association on its next deploy.

  * Content TAGGING is a post-deploy step, NOT a CDK resource. The S3/EXTERNAL
    crawler ingests asynchronously and creates untagged content items; the
    Retrieve tool filters by the `industry=bank` tag AND a per-item `language`
    tag. After the first sync finishes, run the tagging script — it applies the
    base tags and derives the `language` tag (es/pt/en) from each item's
    bank/<lang>/ path:
        python knowledge_bases/tag_kb_content.py --wait --expect 21 --profile <profile>
"""

from __future__ import annotations

from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_connect as connect
from constructs import Construct

import config
from knowledge_bases.knowledge_base import S3KnowledgeBase
from shared import ssm_names


class KnowledgeBaseStack(Stack):
    """Phase 2 — EXTERNAL Q in Connect knowledge base (Spanish) + assistant association."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # EXTERNAL Wisdom KB sourced from the local plain-text (.txt) entries
        # (all languages
        # under knowledge_bases/bank/entries/<lang>/). entries_dir /
        # bucket_prefix come from config (paths are relative to the CDK app
        # root, where cdk runs). The KB resource tag is metadata only — the
        # per-content-item segmentation tags (industry=bank + per-language
        # locale) are applied post-deploy by knowledge_bases/tag_kb_content.py.
        self.kb = S3KnowledgeBase(
            self,
            "KnowledgeBase",
            name=config.KB_NAME,
            entries_dir=config.KB_ENTRIES_DIR,
            description=f"{config.KB_NAME} multi-language self-service KB.",
            bucket_prefix=config.KB_BUCKET_PREFIX,
            # AmazonConnectEnabled=True is REQUIRED for the agent workspace to
            # open KB articles: the Connect service-linked role only allows
            # wisdom:* (GetContent / ListContentAssociations) on resources
            # carrying this tag (SLR statement
            # AllowWisdomForConnectEnabledTaggedResources, condition
            # aws:ResourceTag/AmazonConnectEnabled=True). Connect sets it
            # automatically when a KB is added via its console flow; because we
            # wire the KB<->assistant association directly, we must set it here
            # or articles fail with "We're having trouble loading this content"
            # (AccessDenied on wisdom:GetContent). AmazonConnectInstanceId
            # mirrors Connect's own tagging.
            tags={
                "industry": "bank",
                "AmazonConnectEnabled": "True",
                "AmazonConnectInstanceId": config.INSTANCE_ID,
            },
        )

        # Associate the KB with the Q in Connect AI Agents domain so the agents'
        # Retrieve tool can query it. The association is created here and its id
        # is published to SSM at deploy time (KB_ASSOC_ID) — it is never a
        # hard-coded config value.
        self.assoc = self.kb.associate_with_assistant(config.ASSISTANT_ID)
        assoc_id = self.assoc.attr_assistant_association_id

        # Bind the KB to the Connect INSTANCE as a WISDOM_KNOWLEDGE_BASE
        # integration association. This is the piece that puts the KB's content
        # resources into the SESSION POLICY the agent-workspace api-proxy mints
        # for wisdom:* calls — WITHOUT it, opening a KB article in the workspace
        # fails with "not authorized to perform wisdom:GetContent ... because no
        # session policy allows the action", EVEN when the KB/content carry the
        # AmazonConnectEnabled=True tag (the tag only satisfies the service-
        # linked role's BASE managed policy; the session-policy layer is scoped
        # from the instance's integration associations, not tags). The Connect
        # console creates this association automatically when you "Add
        # integration"; because we wire the KB directly we must create it here.
        # The instance↔assistant (WISDOM_ASSISTANT) association is created
        # separately (console/AI-agents setup); only the KB association is added
        # here. Gated on HAS_REAL_INSTANCE since it is instance-bound.
        #
        # Note: CfnIntegrationAssociation's docs only list LEX_BOT|LAMBDA_FUNCTION
        # for IntegrationType, but the underlying CFN resource accepts the full
        # set (WISDOM_KNOWLEDGE_BASE included); the L1 takes a plain string.
        if config.HAS_REAL_INSTANCE:
            instance_arn = (
                f"arn:aws:connect:{self.region}:{self.account}:instance/{config.INSTANCE_ID}"
            )
            self.kb_integration = connect.CfnIntegrationAssociation(
                self,
                "KbInstanceIntegration",
                instance_id=instance_arn,
                integration_type="WISDOM_KNOWLEDGE_BASE",
                integration_arn=self.kb.knowledge_base_arn,
            )
            self.kb_integration.node.add_dependency(self.kb.knowledge_base)

        # --- publish the cross-stack contract ---
        ssm_names.publish(self, "PKbId", ssm_names.KB_ID, self.kb.knowledge_base_id)
        ssm_names.publish(self, "PKbAssoc", ssm_names.KB_ASSOC_ID, assoc_id)

        # --- human/ops outputs (not on the bus) ---
        CfnOutput(self, "KnowledgeBaseId", value=self.kb.knowledge_base_id)
        CfnOutput(self, "KnowledgeBaseBucket", value=self.kb.bucket_name)
        CfnOutput(self, "KnowledgeBaseAssociationId", value=assoc_id)
