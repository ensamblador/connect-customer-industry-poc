"""
cdk_constructs/webhosting/webhosting_construct.py — static website hosting Construct.

Industry-agnostic. Deploys a Vite-built website to a private S3 bucket served
through CloudFront with Origin Access Control (OAC), plus an optional demo
data-viewer (a Lambda behind a ``/datos*`` CloudFront behavior that renders a
set of DynamoDB tables as HTML).

This construct is parameterized — it does NOT import a top-level ``config``
module. Each per-industry app passes its own values in from its local
``config.py`` (see each app's ``website_stack.py``), so editing this module
changes behavior for every industry app that imports it.

Assets that VARY per industry stay in the industry app and are passed in as
paths:
  * ``assets_path``            — the Vite build output (``website/dist``).
  * ``data_viewer_asset_path`` — the industry's data-viewer Lambda source dir
                                 (branding/table titles live in that handler).

The site is static — the Amazon Connect widget configuration is baked into
index.html, so there are no runtime VITE_* env vars to validate. A synth-time
check confirms the built assets exist (so we never deploy an empty bucket);
build the site with ``npm run build`` in website/ before deploying.
"""

from __future__ import annotations

import os

from aws_cdk import (
    Duration,
    RemovalPolicy,
    CfnOutput,
    Stack,
    aws_s3 as s3,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_s3_deployment as s3deploy,
    aws_lambda as _lambda,
    aws_apigateway as apigateway,
    aws_iam as iam,
)
from constructs import Construct

_PRICE_CLASS_MAP = {
    "PRICE_CLASS_100": cloudfront.PriceClass.PRICE_CLASS_100,
    "PRICE_CLASS_200": cloudfront.PriceClass.PRICE_CLASS_200,
    "PRICE_CLASS_ALL": cloudfront.PriceClass.PRICE_CLASS_ALL,
}
_HTTP_VERSION_MAP = {
    "HTTP1_1": cloudfront.HttpVersion.HTTP1_1,
    "HTTP2": cloudfront.HttpVersion.HTTP2,
    "HTTP2_AND_3": cloudfront.HttpVersion.HTTP2_AND_3,
    "HTTP3": cloudfront.HttpVersion.HTTP3,
}
_VIEWER_PROTOCOL_MAP = {
    "ALLOW_ALL": cloudfront.ViewerProtocolPolicy.ALLOW_ALL,
    "HTTPS_ONLY": cloudfront.ViewerProtocolPolicy.HTTPS_ONLY,
    "REDIRECT_TO_HTTPS": cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
}

# The config attribute names this construct's ``from_config`` helper reads. Kept
# as a module constant so the config CONTRACT is documented in one place.
_CONFIG_KEYS = (
    "WEBSITE_ASSETS_PATH",
    "WEBSITE_PRICE_CLASS",
    "WEBSITE_HTTP_VERSION",
    "WEBSITE_VIEWER_PROTOCOL_POLICY",
    "WEBSITE_DEFAULT_ROOT_OBJECT",
    "WEBSITE_INVALIDATION_PATHS",
    "WEBSITE_DESTINATION_KEY_PREFIX",
)


def _resolve_enum(mapping: dict, key: str, label: str):
    """Look ``key`` up in ``mapping`` with a helpful error on a bad value."""
    try:
        return mapping[key]
    except KeyError:
        valid = ", ".join(sorted(mapping))
        raise ValueError(
            f"cdk_constructs.webhosting: invalid {label} '{key}'. Valid values: {valid}."
        ) from None


class Webhosting(Construct):
    """Private S3 bucket + CloudFront (OAC) serving the built Vite website.

    Parameters
    ----------
    assets_path:
        Absolute path to the built site (Vite ``website/dist``). Validated at
        synth time so an empty bucket is never deployed.
    data_viewer_asset_path:
        Absolute path to the industry's data-viewer Lambda source directory.
        When ``None``, the ``/datos*`` data-viewer behavior is not created.
    data_viewer_tables:
        Mapping of ``ENV_VAR -> table_name`` handed to the data-viewer Lambda.
        The Lambda is granted ``dynamodb:Scan`` on exactly these tables (ARNs
        reconstructed from the names + this stack's account/region, so there is
        no cross-stack import). The tables are created by the industry's Phase 1
        MCP stack; deploy that first.
    price_class / http_version / viewer_protocol_policy / default_root_object /
    invalidation_paths / destination_key_prefix:
        CloudFront + BucketDeployment knobs (string enums resolved internally).
    data_viewer_description:
        Human description used on the data-viewer Lambda + REST API.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        assets_path: str,
        data_viewer_asset_path: str | None = None,
        data_viewer_tables: dict[str, str] | None = None,
        price_class: str = "PRICE_CLASS_100",
        http_version: str = "HTTP2",
        viewer_protocol_policy: str = "REDIRECT_TO_HTTPS",
        default_root_object: str = "index.html",
        invalidation_paths: list[str] | None = None,
        destination_key_prefix: str = "",
        data_viewer_description: str = "Renders the demo DynamoDB tables as an HTML page.",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self._assets_path = assets_path
        self._data_viewer_asset_path = data_viewer_asset_path
        self._data_viewer_tables = data_viewer_tables or {}
        self._price_class = price_class
        self._http_version = http_version
        self._viewer_protocol_policy = viewer_protocol_policy
        self._default_root_object = default_root_object
        self._invalidation_paths = invalidation_paths or ["/index.html"]
        self._destination_key_prefix = destination_key_prefix
        self._data_viewer_description = data_viewer_description

        # Barrier — confirm the built assets exist before declaring resources.
        self._validate_assets()
        self._create_resources()

    # --------------------------------------------------------------------- #
    # Config-driven convenience constructor
    # --------------------------------------------------------------------- #
    @classmethod
    def from_config(
        cls,
        scope: Construct,
        construct_id: str,
        *,
        config,
        project_root: str | None = None,
        data_viewer_subdir: str = os.path.join("lambdas", "code", "data_viewer"),
        data_viewer_tables: dict[str, str] | None = None,
        data_viewer_description: str = "Renders the demo DynamoDB tables as an HTML page.",
        **kwargs,
    ) -> "Webhosting":
        """Build a ``Webhosting`` from a per-industry ``config`` module.

        Reads the standard WEBSITE_* contract (see ``_CONFIG_KEYS``) plus the
        three table-name constants, resolving relative paths against the
        directory that holds ``config.py``. This keeps the config→props wiring
        in ONE place instead of duplicated across every app's ``website_stack``.

        Override any piece via kwargs (e.g. a custom ``data_viewer_tables`` map
        once table env-var names are neutralized), or bypass this helper and
        call the plain constructor with explicit props.
        """
        root = project_root or os.path.dirname(os.path.abspath(config.__file__))
        # Default env→table map. NOTE: the ``PLANS_TABLE`` / ``LINES_TABLE``
        # keys are legacy names still read by each app's data-viewer Lambda;
        # override this map (and the handler) as part of the neutral-naming pass.
        tables = data_viewer_tables or {
            "ACCOUNTS_TABLE": config.ACCOUNTS_TABLE_NAME,
            "PLANS_TABLE": config.PLANS_TABLE_NAME,
            "LINES_TABLE": config.LINES_TABLE_NAME,
        }
        return cls(
            scope,
            construct_id,
            assets_path=os.path.join(root, config.WEBSITE_ASSETS_PATH),
            data_viewer_asset_path=os.path.join(root, data_viewer_subdir),
            data_viewer_tables=tables,
            price_class=config.WEBSITE_PRICE_CLASS,
            http_version=config.WEBSITE_HTTP_VERSION,
            viewer_protocol_policy=config.WEBSITE_VIEWER_PROTOCOL_POLICY,
            default_root_object=config.WEBSITE_DEFAULT_ROOT_OBJECT,
            invalidation_paths=config.WEBSITE_INVALIDATION_PATHS,
            destination_key_prefix=config.WEBSITE_DESTINATION_KEY_PREFIX,
            data_viewer_description=data_viewer_description,
            **kwargs,
        )

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #
    @property
    def distribution_domain_name(self) -> str:
        """The CloudFront distribution domain (e.g. ``d111.cloudfront.net``)."""
        return self.distribution.distribution_domain_name

    @property
    def bucket_name(self) -> str:
        """The private site bucket's name."""
        return self.site_bucket.bucket_name

    # --------------------------------------------------------------------- #
    # Synth-time validation barrier
    # --------------------------------------------------------------------- #
    def _validate_assets(self) -> None:
        if not os.path.isdir(self._assets_path):
            raise FileNotFoundError(
                f"No se encontró el directorio de assets del Website en "
                f"'{self._assets_path}'. Ejecuta 'npm run build' en website/ "
                f"antes de desplegar (o pon config.BUILD_WEBSITE=False para "
                f"omitir el hosting del sitio)."
            )

    # --------------------------------------------------------------------- #
    # Demo data viewer (DynamoDB tables -> HTML)
    # --------------------------------------------------------------------- #
    def _create_data_viewer_origin(self) -> "origins.RestApiOrigin":
        """Create the data-viewer Lambda + a REST API, returned as a CloudFront origin.

        The Lambda scans the ``data_viewer_tables`` and renders them as HTML. It
        is fronted by a regional API Gateway REST API (Lambda proxy integration,
        GET /datos) which CloudFront uses as the origin for the ``/datos*``
        behavior. API Gateway (rather than a Lambda Function URL) is used because
        Function URL + CloudFront OAC has recurring SigV4 403 failures; a REST
        API origin is the reliable, conventional pattern.

        The function is granted ``dynamodb:Scan`` on exactly the given tables.
        """
        stack = Stack.of(self)
        table_arns = []
        for name in self._data_viewer_tables.values():
            arn = f"arn:aws:dynamodb:{stack.region}:{stack.account}:table/{name}"
            table_arns.extend([arn, f"{arn}/index/*"])

        fn = _lambda.Function(
            self,
            "DataViewerFn",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=_lambda.Code.from_asset(self._data_viewer_asset_path),
            timeout=Duration.seconds(30),
            memory_size=256,
            environment=dict(self._data_viewer_tables),
            description=self._data_viewer_description,
        )
        fn.add_to_role_policy(
            iam.PolicyStatement(actions=["dynamodb:Scan"], resources=table_arns)
        )

        # Regional REST API (no API key — public read of synthetic demo data),
        # fronted by CloudFront. REGIONAL endpoint avoids a second CloudFront
        # layer in front of this distribution. The handler already returns the
        # Lambda-proxy response shape ({statusCode, headers, body}).
        api = apigateway.LambdaRestApi(
            self,
            "DataViewerApi",
            handler=fn,
            proxy=False,
            endpoint_types=[apigateway.EndpointType.REGIONAL],
            deploy_options=apigateway.StageOptions(stage_name="prod"),
            description=self._data_viewer_description,
        )
        # GET /datos -> Lambda. The CloudFront /datos* behavior maps to the
        # REST API origin (RestApiOrigin appends the /prod stage path).
        datos = api.root.add_resource("datos")
        datos.add_method("GET")

        self.data_viewer_fn = fn
        self.data_viewer_api = api
        return origins.RestApiOrigin(api)

    # --------------------------------------------------------------------- #
    # Resources
    # --------------------------------------------------------------------- #
    def _create_resources(self) -> None:
        assets_path = self._assets_path

        # Private S3 bucket — reachable only through CloudFront OAC.
        self.site_bucket = s3.Bucket(
            self, "SiteBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # Demo data-viewer Lambda + its CloudFront origin (path /datos*). Only
        # built when an asset path + tables were provided.
        build_data_viewer = bool(self._data_viewer_asset_path and self._data_viewer_tables)
        data_viewer_origin = (
            self._create_data_viewer_origin() if build_data_viewer else None
        )

        # Origin Access Control for the S3 origin. CloudFront OAC names are
        # ACCOUNT-GLOBAL (CloudFront is not regional), and the name CDK derives
        # by default comes from the construct path only — so deploying this same
        # stack in a second region collides with "OriginAccessControl ... already
        # exists". Give it an explicit name scoped by stack + region so each
        # region gets its own OAC. (stack.region resolves to the real region,
        # or to the AWS::Region intrinsic when the env is unbound.)
        stack = Stack.of(self)
        site_oac = cloudfront.S3OriginAccessControl(
            self, "SiteOac",
            origin_access_control_name=f"{stack.stack_name}-site-oac-{stack.region}",
        )

        additional_behaviors = {}
        if data_viewer_origin is not None:
            # /datos* -> the data-viewer Lambda. Caching disabled so the page
            # always reflects the current table contents.
            additional_behaviors["/datos*"] = cloudfront.BehaviorOptions(
                origin=data_viewer_origin,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_GET_HEAD,
                cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
            )

        self.distribution = cloudfront.Distribution(
            self, "SiteDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(
                    self.site_bucket, origin_access_control=site_oac
                ),
                viewer_protocol_policy=_resolve_enum(
                    _VIEWER_PROTOCOL_MAP, self._viewer_protocol_policy, "viewer_protocol_policy"
                ),
                compress=True,
            ),
            additional_behaviors=additional_behaviors or None,
            default_root_object=self._default_root_object,
            price_class=_resolve_enum(_PRICE_CLASS_MAP, self._price_class, "price_class"),
            http_version=_resolve_enum(_HTTP_VERSION_MAP, self._http_version, "http_version"),
            # Standard SPA-style error mapping → serve index.html on 403/404.
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.seconds(0),
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.seconds(0),
                ),
            ],
        )

        s3deploy.BucketDeployment(
            self, "DeploySite",
            sources=[s3deploy.Source.asset(assets_path)],
            destination_bucket=self.site_bucket,
            destination_key_prefix=self._destination_key_prefix or None,
            distribution=self.distribution,
            distribution_paths=self._invalidation_paths,
        )

        CfnOutput(self, "WebsiteDistributionDomainName",
                  value=f"https://{self.distribution.distribution_domain_name}",
                  description="CloudFront distribution URL for the website")
        CfnOutput(self, "WebsiteDistributionId",
                  value=self.distribution.distribution_id,
                  description="CloudFront distribution ID for the website")
        CfnOutput(self, "WebsiteBucketName",
                  value=self.site_bucket.bucket_name,
                  description="S3 bucket name for the website")
        if data_viewer_origin is not None:
            CfnOutput(self, "WebsiteDataViewerPath",
                      value=f"https://{self.distribution.distribution_domain_name}/datos",
                      description="URL of the demo data viewer")
