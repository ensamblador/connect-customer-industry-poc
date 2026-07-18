"""
tests/unit/test_website_template.py — CX-AIRLINE-WEBSITE (Phase 6) asserts.

Synthesize a fresh ``WebsiteStack`` (``config.BUILD_WEBSITE`` is True and
``website/dist/index.html`` exists, so the ``Webhosting`` construct
synthesizes) and assert the Phase-6 hosting contract against the resulting
CloudFormation template:

  * a private S3 bucket with ALL public access blocked — the
    ``AWS::S3::Bucket`` carries a ``PublicAccessBlockConfiguration`` with
    ``BlockPublicAcls`` / ``BlockPublicPolicy`` / ``IgnorePublicAcls`` /
    ``RestrictPublicBuckets`` all True (Requirement 9.1);
  * the CloudFront distribution is served via Origin Access Control — an
    ``AWS::CloudFront::OriginAccessControl`` exists and is referenced from the
    distribution's origin config (Requirement 9.1);
  * the ``/datos*`` demo data-viewer behavior — the distribution's
    ``CacheBehaviors`` contains a behavior whose ``PathPattern`` matches
    ``datos*`` (Requirement 9.5).

Validates: Requirements 9.1, 9.5
"""

from __future__ import annotations

import pytest
import aws_cdk as cdk
from aws_cdk.assertions import Template, Match

import config
from agentic_cx_airline.website_stack import WebsiteStack


@pytest.fixture(scope="module")
def template() -> Template:
    """Synthesize a fresh WebsiteStack once and expose its template."""
    assert config.BUILD_WEBSITE, (
        "this suite requires BUILD_WEBSITE=True so the Webhosting construct synthesizes"
    )
    app = cdk.App()
    stack = WebsiteStack(app, "CX-AIRLINE-WEBSITE")
    return Template.from_stack(stack)


# --------------------------------------------------------------------------- #
# Requirement 9.1 — private S3 bucket (all public access blocked)
# --------------------------------------------------------------------------- #

def test_s3_bucket_blocks_all_public_access(template: Template):
    """The site bucket blocks all four public-access vectors."""
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            }
        },
    )


# --------------------------------------------------------------------------- #
# Requirement 9.1 — CloudFront distribution served via Origin Access Control
# --------------------------------------------------------------------------- #

def test_origin_access_control_exists(template: Template):
    """An OAC resource is provisioned for the distribution's S3 origin."""
    template.resource_count_is("AWS::CloudFront::OriginAccessControl", 1)


def test_distribution_references_origin_access_control(template: Template):
    """The distribution's S3 origin references the OAC (OriginAccessControlId)."""
    template.has_resource_properties(
        "AWS::CloudFront::Distribution",
        {
            "DistributionConfig": {
                "Origins": Match.array_with(
                    [
                        Match.object_like(
                            {
                                "OriginAccessControlId": Match.any_value(),
                            }
                        )
                    ]
                )
            }
        },
    )


# --------------------------------------------------------------------------- #
# Requirement 9.5 — the /datos* data-viewer cache behavior
# --------------------------------------------------------------------------- #

def test_datos_cache_behavior_present(template: Template):
    """The distribution has a cache behavior for the data viewer (PathPattern datos*)."""
    template.has_resource_properties(
        "AWS::CloudFront::Distribution",
        {
            "DistributionConfig": {
                "CacheBehaviors": Match.array_with(
                    [
                        Match.object_like(
                            {
                                "PathPattern": Match.string_like_regexp(r"datos\*?"),
                            }
                        )
                    ]
                )
            }
        },
    )


def test_datos_behavior_path_pattern_exact(template: Template):
    """Locate the /datos* behavior explicitly and assert its PathPattern."""
    distributions = template.find_resources("AWS::CloudFront::Distribution")
    assert len(distributions) == 1, "expected exactly one CloudFront distribution"

    (dist,) = distributions.values()
    behaviors = dist["Properties"]["DistributionConfig"].get("CacheBehaviors", [])
    patterns = [b.get("PathPattern") for b in behaviors]
    assert any(p and "datos" in p for p in patterns), (
        f"no /datos* cache behavior found; PathPatterns present: {patterns}"
    )
