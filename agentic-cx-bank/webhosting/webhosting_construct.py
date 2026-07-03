"""
webhosting/webhosting_construct.py — static website hosting as a CDK Construct.

Deploys the Vite-built website (config.WEBSITE_ASSETS_PATH) to a private S3
bucket served through CloudFront with Origin Access Control. Formerly a
standalone CDK app/stack; now a Construct instantiated by the main stack so
the website ships with the rest of the infrastructure-as-code.

The site is static — the Amazon Connect widget configuration is baked into
index.html, so there are no runtime VITE_* env vars to validate. A synth-time
check confirms the built assets exist (so we never deploy an empty bucket);
build the site with `npm run build` in website/ before deploying.

All configuration is read from the flat top-level `config` module; paths are
resolved relative to the CDK project root (where config.py lives) so synth is
independent of the cwd.
"""

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

import config

# Project root = the directory holding the main config.py. Config paths
# (e.g. WEBSITE_ASSETS_PATH) are declared relative to it.
_PROJECT_ROOT = os.path.dirname(os.path.abspath(config.__file__))
# The demo data-viewer Lambda source lives alongside this construct.
_DATA_VIEWER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_viewer_lambda")

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


def _resolve_path(path: str) -> str:
    """Resolve a config path against the CDK project root."""
    if os.path.isabs(path):
        return path
    return os.path.normpath(os.path.join(_PROJECT_ROOT, path))


class Webhosting(Construct):
    """Private S3 bucket + CloudFront (OAC) serving the built Vite website."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        # Barrier — confirm the built assets exist before declaring resources.
        self._validate_assets()
        self._create_resources()

    # --------------------------------------------------------------------- #
    # Synth-time validation barrier
    # --------------------------------------------------------------------- #
    def _validate_assets(self) -> None:
        assets_path = _resolve_path(config.WEBSITE_ASSETS_PATH)
        if not os.path.isdir(assets_path):
            raise FileNotFoundError(
                f"No se encontró el directorio de assets del Website en "
                f"'{config.WEBSITE_ASSETS_PATH}'. Ejecuta 'npm run build' en "
                f"website/ antes de desplegar (o pon config.BUILD_WEBSITE=False "
                f"para omitir el hosting del sitio)."
            )

    # --------------------------------------------------------------------- #
    # Demo data viewer (DynamoDB tables -> HTML)
    # --------------------------------------------------------------------- #
    def _create_data_viewer_origin(self) -> "origins.RestApiOrigin":
        """Create the data-viewer Lambda + a REST API, returned as a CloudFront origin.

        The Lambda scans the three banking tables (accounts/products/cards) and
        renders them as HTML. It is fronted by a regional API Gateway REST API
        (Lambda proxy integration, GET /datos) which CloudFront uses as the
        origin for the ``/datos*`` behavior. API Gateway (rather than a Lambda
        Function URL) is used because Function URL + CloudFront OAC has
        recurring SigV4 403 failures; a REST API origin is the reliable,
        conventional pattern.

        The function is granted ``dynamodb:Scan`` on exactly the three tables
        (ARNs reconstructed from the config names + this stack's account/region,
        so there is no cross-stack import). The tables themselves are created by
        Phase 1 (CX-BANCO-MCP); deploy that stack first.
        """
        stack = Stack.of(self)
        table_names = [
            config.ACCOUNTS_TABLE_NAME,
            config.PLANS_TABLE_NAME,
            config.LINES_TABLE_NAME,
        ]
        table_arns = []
        for name in table_names:
            arn = f"arn:aws:dynamodb:{stack.region}:{stack.account}:table/{name}"
            table_arns.extend([arn, f"{arn}/index/*"])

        fn = _lambda.Function(
            self,
            "DataViewerFn",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=_lambda.Code.from_asset(_DATA_VIEWER_DIR),
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "ACCOUNTS_TABLE": config.ACCOUNTS_TABLE_NAME,
                "PLANS_TABLE": config.PLANS_TABLE_NAME,
                "LINES_TABLE": config.LINES_TABLE_NAME,
            },
            description="Renders the banking demo DynamoDB tables as an HTML page.",
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
            description="Demo data viewer for the banking DynamoDB tables.",
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
        assets_path = _resolve_path(config.WEBSITE_ASSETS_PATH)

        # Private S3 bucket — reachable only through CloudFront OAC.
        self.site_bucket = s3.Bucket(
            self, "SiteBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # Demo data-viewer Lambda + its CloudFront origin (path /datos*). It
        # renders the three backend DynamoDB tables as a styled HTML page.
        data_viewer_origin = self._create_data_viewer_origin()

        self.distribution = cloudfront.Distribution(
            self, "SiteDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(self.site_bucket),
                viewer_protocol_policy=_VIEWER_PROTOCOL_MAP[config.WEBSITE_VIEWER_PROTOCOL_POLICY],
                compress=True,
            ),
            # /datos* -> the data-viewer Lambda (Function URL via OAC). Caching
            # disabled so the page always reflects the current table contents.
            additional_behaviors={
                "/datos*": cloudfront.BehaviorOptions(
                    origin=data_viewer_origin,
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    allowed_methods=cloudfront.AllowedMethods.ALLOW_GET_HEAD,
                    cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                ),
            },
            default_root_object=config.WEBSITE_DEFAULT_ROOT_OBJECT,
            price_class=_PRICE_CLASS_MAP[config.WEBSITE_PRICE_CLASS],
            http_version=_HTTP_VERSION_MAP[config.WEBSITE_HTTP_VERSION],
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=err["http_status"],
                    response_http_status=err["response_http_status"],
                    response_page_path=err["response_page_path"],
                    ttl=Duration.seconds(err["ttl_seconds"]),
                )
                for err in config.WEBSITE_ERROR_RESPONSES
            ],
        )

        s3deploy.BucketDeployment(
            self, "DeploySite",
            sources=[s3deploy.Source.asset(assets_path)],
            destination_bucket=self.site_bucket,
            destination_key_prefix=config.WEBSITE_DESTINATION_KEY_PREFIX or None,
            distribution=self.distribution,
            distribution_paths=config.WEBSITE_INVALIDATION_PATHS,
        )

        CfnOutput(self, "WebsiteDistributionDomainName",
                  value=self.distribution.distribution_domain_name,
                  description="CloudFront distribution URL for the website")
        CfnOutput(self, "WebsiteDistributionId",
                  value=self.distribution.distribution_id,
                  description="CloudFront distribution ID for the website")
        CfnOutput(self, "WebsiteBucketName",
                  value=self.site_bucket.bucket_name,
                  description="S3 bucket name for the website")
        CfnOutput(self, "WebsiteDataViewerPath",
                  value=f"https://{self.distribution.distribution_domain_name}/datos",
                  description="URL of the demo data viewer (accounts/products/cards)")
