"""
cdk_constructs/knowledge_bases/knowledge_base.py — reusable Q in Connect (Wisdom) knowledge
base, backed by an S3 document source.

Modular + reusable: instantiate `S3KnowledgeBase` once per knowledge base.
It provisions the whole EXTERNAL-KB chain so callers don't repeat it:

    KMS key
       |
    S3 bucket  (+ bucket policy granting app-integrations.amazonaws.com read)
       |  BucketDeployment uploads the local plain-text (.txt) entries
       v
    AppIntegrations DataIntegration   (SourceURI = s3://<bucket>)
       |
       v
    Wisdom CfnKnowledgeBase (type EXTERNAL, source = the DataIntegration ARN)

Optionally associate the KB with an existing Q in Connect assistant via
`associate_with_assistant(assistant_id)` so the agent's Retrieve tool can
query it. NOTE: an assistant supports only ONE knowledge-base association; to
use several KBs with one assistant, surface them as multiple Retrieve tools on
an orchestration AI agent rather than associating them all here.

Why EXTERNAL (not CUSTOM): EXTERNAL knowledge bases synchronize their content
from a source (here S3) automatically. For Amazon S3, the AppIntegrations
DataIntegration's SourceURI is `s3://<bucket>` and the bucket policy must let
app-integrations.amazonaws.com do s3:ListBucket / s3:GetObject /
s3:GetBucketLocation.

One bucket per KB (by design)
-----------------------------
The S3 DataIntegration SourceURI is the WHOLE bucket (`s3://<bucket>`);
AppIntegrations has no prefix/object filter for S3 (FileConfiguration /
ObjectConfiguration must be null), so a KB ingests EVERY object in its bucket.
We therefore give each KB its own dedicated bucket — clean isolation. To serve
several domains, create several `S3KnowledgeBase` instances (each its own
bucket + KB id) and point each AI agent / Retrieve tool at the KB id it needs.

CRITICAL — AWS::Wisdom::KnowledgeBase does NOT support updates. Never change a
property that feeds the KB or the KMS key it references (KB name, source config,
KMS key arn or its key policy) on an existing stack — CloudFormation fails with
"Update operation is not supported" and can leave the stack in
UPDATE_ROLLBACK_FAILED. Such changes require a replacement (two-step deploy:
toggle the KB off, deploy, on, deploy).
"""

from __future__ import annotations

from aws_cdk import RemovalPolicy
from aws_cdk import aws_appintegrations as appintegrations
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms as kms
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from aws_cdk import aws_wisdom as wisdom
from constructs import Construct


class S3KnowledgeBase(Construct):
    """An EXTERNAL Q in Connect knowledge base sourced from an S3 bucket."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        name: str,
        entries_dir: str,
        description: str = "",
        bucket_prefix: str | None = None,
        tags: dict[str, str] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self._name = name
        # Optional logical folder the entries live under inside the bucket.
        # When None (default), entries go to the BUCKET ROOT — which is what
        # the deployed KBs use. Organizational only — the S3
        # DataIntegration SourceURI is the whole bucket, so the crawler
        # ingests every object regardless of prefix. Do NOT default this to
        # the KB name: changing the prefix re-keys the BucketDeployment, which
        # churns the bucket and cascades a KB update (Wisdom has no update
        # path → deploy fails).
        self._prefix = bucket_prefix.strip("/") if bucket_prefix else None
        self._tags = tags or {}

        self._create_bucket()
        self._upload_entries(entries_dir)
        self._create_data_integration(description)
        self._create_knowledge_base(description)

    # ------------------------------------------------------------------ #
    def _create_bucket(self) -> None:
        # KMS key: AWS::AppIntegrations::DataIntegration requires KmsKey, the
        # KB's server-side encryption uses it, and it encrypts the bucket at
        # rest. Keep this STABLE — changing the key (or its policy) forces a KB
        # update, which Wisdom does not support.
        self.key = kms.Key(
            self,
            "Key",
            description=f"KMS key for the {self._name} knowledge base bucket.",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # The Q in Connect / Wisdom service must be able to DECRYPT content with
        # this CMK to render an article in the agent assistant panel
        # (wisdom-v2/article). Ingestion and Retrieve text work via grants made
        # at create time, but the article-view path decrypts as the service
        # principal directly — without this statement the panel fails with
        # "We're having trouble loading this content." Mirrors the key policy of
        # working EXTERNAL S3 knowledge bases.
        self.key.add_to_resource_policy(
            iam.PolicyStatement(
                sid="AllowWisdomServiceUseOfKey",
                effect=iam.Effect.ALLOW,
                principals=[iam.ServicePrincipal("wisdom.amazonaws.com")],
                actions=["kms:Decrypt", "kms:DescribeKey"],
                resources=["*"],
            )
        )

        self.bucket = s3.Bucket(
            self,
            "Bucket",
            encryption=s3.BucketEncryption.KMS,
            encryption_key=self.key,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,  # demo; RETAIN in production
            auto_delete_objects=True,
        )

        # AppIntegrations (the EXTERNAL KB crawler) must read the bucket.
        self.bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid="AllowAppIntegrationsRead",
                effect=iam.Effect.ALLOW,
                principals=[iam.ServicePrincipal("app-integrations.amazonaws.com")],
                actions=["s3:ListBucket", "s3:GetObject", "s3:GetBucketLocation"],
                resources=[self.bucket.bucket_arn, self.bucket.arn_for_objects("*")],
            )
        )

    # ------------------------------------------------------------------ #
    def _upload_entries(self, entries_dir: str) -> None:
        # Upload the local plain-text (.txt) entries. When self._prefix is set
        # they go under
        # that logical folder; when None they go to the bucket ROOT (the
        # deployed default). Logical separation only — the AppIntegrations
        # crawler ingests EVERY object in the bucket regardless of prefix. CDK
        # zips the folder at synth and a custom resource syncs it on deploy.
        kwargs = {}
        if self._prefix:
            kwargs["destination_key_prefix"] = self._prefix
        self.deployment = s3deploy.BucketDeployment(
            self,
            "Entries",
            sources=[s3deploy.Source.asset(entries_dir)],
            destination_bucket=self.bucket,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    def _create_data_integration(self, description: str) -> None:
        # The AppIntegrations DataIntegration that points the KB crawler at S3.
        # For Amazon S3, SourceURI is s3://<bucket> and file/object config must
        # be null (omitted).
        #
        # IMPORTANT: name the DataIntegration EXACTLY the same as the knowledge
        # base. The Amazon Q in Connect console resolves a KB's integration by
        # looking up a DataIntegration whose identifier == the KB name; a
        # different name (e.g. a "-source" suffix) makes the console fail with
        # "Could not find DataIntegration with identifier: <kb name>" even
        # though the KB itself works.
        self.data_integration = appintegrations.CfnDataIntegration(
            self,
            "DataIntegration",
            name=self._name,
            kms_key=self.key.key_arn,
            source_uri=f"s3://{self.bucket.bucket_name}",
            description=description or f"S3 source for the {self._name} KB.",
        )
        # The integration reads via the bucket policy; ensure ordering.
        self.data_integration.node.add_dependency(self.bucket)

    # ------------------------------------------------------------------ #
    def _create_knowledge_base(self, description: str) -> None:
        self.knowledge_base = wisdom.CfnKnowledgeBase(
            self,
            "KnowledgeBase",
            name=self._name,
            knowledge_base_type="EXTERNAL",
            description=description or f"{self._name} knowledge base.",
            source_configuration=wisdom.CfnKnowledgeBase.SourceConfigurationProperty(
                app_integrations=wisdom.CfnKnowledgeBase.AppIntegrationsConfigurationProperty(
                    app_integration_arn=self.data_integration.attr_data_integration_arn,
                )
            ),
            server_side_encryption_configuration=wisdom.CfnKnowledgeBase.ServerSideEncryptionConfigurationProperty(
                kms_key_id=self.key.key_arn,
            ),
            tags=[{"key": k, "value": v} for k, v in self._tags.items()] or None,
        )
        self.knowledge_base.node.add_dependency(self.data_integration)
        # On a FRESH create, ensure the entries are uploaded before the KB so
        # its first sync sees content. (Safe here because the KB is only ever
        # created or deleted as a whole — never updated in place. The KB lives
        # in its own stack now, so a rebuild is a destroy + deploy of that
        # stack. AWS::Wisdom::KnowledgeBase has no update path, so never put it
        # in a changeset that merely tweaks the entries/bucket on an EXISTING
        # KB; rebuild the stack instead.)
        self.knowledge_base.node.add_dependency(self.deployment)

    # ------------------------------------------------------------------ #
    def associate_with_assistant(
        self, assistant_id: str
    ) -> wisdom.CfnAssistantAssociation:
        """
        Associate this KB with an existing Q in Connect assistant so the
        agent's Retrieve tool can query it. Returns the association construct.

        NOTE: an assistant supports only ONE knowledge-base association. To use
        several KBs with one assistant, surface them as multiple Retrieve tools
        on an orchestration AI agent rather than associating them all here.
        """
        association = wisdom.CfnAssistantAssociation(
            self,
            "AssistantAssociation",
            assistant_id=assistant_id,
            association_type="KNOWLEDGE_BASE",
            association=wisdom.CfnAssistantAssociation.AssociationDataProperty(
                knowledge_base_id=self.knowledge_base.attr_knowledge_base_id,
            ),
        )
        association.node.add_dependency(self.knowledge_base)
        return association

    # ------------------------------------------------------------------ #
    @property
    def knowledge_base_id(self) -> str:
        return self.knowledge_base.attr_knowledge_base_id

    @property
    def knowledge_base_arn(self) -> str:
        return self.knowledge_base.attr_knowledge_base_arn

    @property
    def bucket_name(self) -> str:
        return self.bucket.bucket_name
