"""
apis/telco_api.py — Amazon API Gateway REST API for the telco backend.

Following the project convention, ALL API Gateway constructs for the project
live under `apis/`. This module exposes the telco self-service REST surface
that the Bedrock AgentCore gateway re-exposes as MCP tools.

Resource map (operationId in parentheses — the MCP tool name):

    GET  /accounts/{accountId}            -> accounts_fn  (getAccount)
    GET  /accounts/{accountId}/balance    -> accounts_fn  (getAccountBalance)
    GET  /accounts?phoneNumber=+1...      -> accounts_fn  (getAccountByPhone)
    GET  /accounts/by-email?email=...     -> accounts_fn  (getAccountByEmail)
    GET  /plans?minGb=25                  -> plans_fn     (listPlans)
    GET  /plans/{planId}                  -> plans_fn     (getPlan)
    POST /lines                           -> lines_fn     (newLine)
    GET  /lines?customerId=cust-...       -> lines_fn     (listCustomerLines)
    GET  /lines/{lineId}                  -> lines_fn     (getLine)

API key authentication
-----------------------
When `require_api_key=True`, every method requires an API key (x-api-key
header) and a usage plan ties the key to the stage. The key VALUE comes from a
Secrets Manager secret (the single source of truth), so the SAME value feeds
the AgentCore API Key credential provider. The plaintext key is never written
into the CDK code or the synthesized template.

Every method declares method responses and an operation name so the exported
OpenAPI carries `responses` and `operationId`.
"""

from __future__ import annotations

from aws_cdk import aws_apigateway as apigw
from aws_cdk import aws_lambda as aws_lambda
from aws_cdk import aws_secretsmanager as sm
from constructs import Construct

_DEFAULT_METHOD_RESPONSES = [
    apigw.MethodResponse(status_code="200"),
    apigw.MethodResponse(status_code="201"),
    apigw.MethodResponse(status_code="400"),
    apigw.MethodResponse(status_code="404"),
]

# JSON key inside the secret that holds the API key string.
SECRET_API_KEY_JSON_KEY = "apiKey"


class TelcoApi(Construct):
    """REST API for the telco self-service backend."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        api_name: str,
        stage_name: str,
        accounts_fn: aws_lambda.IFunction,
        plans_fn: aws_lambda.IFunction,
        lines_fn: aws_lambda.IFunction,
        require_api_key: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self._require_api_key = require_api_key

        self.api = apigw.RestApi(
            self,
            "RestApi",
            rest_api_name=api_name,
            description="Telco self-service backend (accounts, plans, support).",
            deploy_options=apigw.StageOptions(stage_name=stage_name),
            endpoint_types=[apigw.EndpointType.REGIONAL],
        )

        accounts_i = apigw.LambdaIntegration(accounts_fn)
        plans_i = apigw.LambdaIntegration(plans_fn)
        lines_i = apigw.LambdaIntegration(lines_fn)

        # ---- /accounts -------------------------------------------------- #
        accounts = self.api.root.add_resource("accounts")
        # GET /accounts?phoneNumber=... (lookup by phone)
        self._add_method(
            accounts,
            "GET",
            accounts_i,
            operation_name="getAccountByPhone",
            request_parameters={"method.request.querystring.phoneNumber": False},
        )
        account = accounts.add_resource("{accountId}")
        self._add_method(account, "GET", accounts_i, operation_name="getAccount")
        self._add_method(
            account.add_resource("balance"),
            "GET",
            accounts_i,
            operation_name="getAccountBalance",
        )
        # GET /accounts/by-email?email=... (lookup by email; literal segment
        # takes routing priority over {accountId})
        self._add_method(
            accounts.add_resource("by-email"),
            "GET",
            accounts_i,
            operation_name="getAccountByEmail",
            request_parameters={"method.request.querystring.email": False},
        )

        # ---- /plans ----------------------------------------------------- #
        plans = self.api.root.add_resource("plans")
        self._add_method(
            plans,
            "GET",
            plans_i,
            operation_name="listPlans",
            request_parameters={"method.request.querystring.minGb": False},
        )
        self._add_method(
            plans.add_resource("{planId}"), "GET", plans_i, operation_name="getPlan"
        )

        # ---- /lines ----------------------------------------------------- #
        lines = self.api.root.add_resource("lines")
        # POST /lines (request a new line)
        self._add_method(lines, "POST", lines_i, operation_name="newLine")
        # GET /lines?customerId=... (list a customer's line requests)
        self._add_method(
            lines,
            "GET",
            lines_i,
            operation_name="listCustomerLines",
            request_parameters={"method.request.querystring.customerId": False},
        )
        self._add_method(
            lines.add_resource("{lineId}"), "GET", lines_i, operation_name="getLine"
        )

        # API key + usage plan, keyed off a Secrets Manager secret.
        self.api_key_secret: sm.Secret | None = None
        if require_api_key:
            self._set_up_api_key()

    # ------------------------------------------------------------------ #
    def _add_method(
        self,
        resource: apigw.IResource,
        http_method: str,
        integration: apigw.Integration,
        *,
        operation_name: str,
        request_parameters: dict[str, bool] | None = None,
    ) -> apigw.Method:
        """Method with operation name, method responses, and (optionally) an
        enforced API key."""
        return resource.add_method(
            http_method,
            integration,
            operation_name=operation_name,
            request_parameters=request_parameters,
            method_responses=_DEFAULT_METHOD_RESPONSES,
            api_key_required=self._require_api_key,
        )

    # ------------------------------------------------------------------ #
    def _set_up_api_key(self) -> None:
        """Create the secret (source of truth for the key), the API Gateway
        ApiKey seeded from it, and a usage plan binding the key to the stage."""
        self.api_key_secret = sm.Secret(
            self,
            "ApiKeySecret",
            description="Telco self-service API key (API Gateway + AgentCore).",
            generate_secret_string=sm.SecretStringGenerator(
                secret_string_template="{}",
                generate_string_key=SECRET_API_KEY_JSON_KEY,
                exclude_punctuation=True,
                password_length=40,
            ),
        )
        key_value = self.api_key_secret.secret_value_from_json(
            SECRET_API_KEY_JSON_KEY
        ).unsafe_unwrap()

        self.api_key = self.api.add_api_key(
            "TelcoApiKey",
            api_key_name="telco-selfservice-api-key",
            value=key_value,
        )
        self.usage_plan = self.api.add_usage_plan(
            "TelcoUsagePlan", name="telco-selfservice-usage-plan"
        )
        self.usage_plan.add_api_key(self.api_key)
        self.usage_plan.add_api_stage(stage=self.api.deployment_stage)

    # ------------------------------------------------------------------ #
    @property
    def rest_api_id(self) -> str:
        return self.api.rest_api_id

    @property
    def stage_name(self) -> str:
        return self.api.deployment_stage.stage_name
