"""
apis/airline_api.py — Amazon API Gateway REST API for the airline backend.

Following the project convention, ALL API Gateway constructs for the project
live under `apis/`. This module exposes the airline self-service REST surface
that the Bedrock AgentCore gateway re-exposes as MCP tools.

Resource map (operationId in parentheses — the MCP tool name):

    GET  /accounts/{accountId}            -> accounts_fn  (getAccount)
    GET  /accounts/{accountId}/balance    -> accounts_fn  (getAccountBalance)
    GET  /accounts?phoneNumber=+1...      -> accounts_fn  (getAccountByPhone)
    GET  /accounts/by-email?email=...     -> accounts_fn  (getAccountByEmail)
    GET  /products?maxAnnualFee=100       -> products_fn  (listProducts)
    GET  /products/{productId}            -> products_fn  (getProduct)
    POST /cards                           -> cards_fn     (requestCard)
    GET  /cards?customerId=cust-...       -> cards_fn     (listCustomerCards)
    GET  /cards/{cardId}                  -> cards_fn     (getCard)

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


class AirlineApi(Construct):
    """REST API for the airline self-service backend."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        api_name: str,
        stage_name: str,
        accounts_fn: aws_lambda.IFunction,
        products_fn: aws_lambda.IFunction,
        cards_fn: aws_lambda.IFunction,
        require_api_key: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self._require_api_key = require_api_key

        self.api = apigw.RestApi(
            self,
            "RestApi",
            rest_api_name=api_name,
            description="Airline self-service backend (accounts, products, cards).",
            deploy_options=apigw.StageOptions(stage_name=stage_name),
            endpoint_types=[apigw.EndpointType.REGIONAL],
        )

        accounts_i = apigw.LambdaIntegration(accounts_fn)
        products_i = apigw.LambdaIntegration(products_fn)
        cards_i = apigw.LambdaIntegration(cards_fn)

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

        # ---- /products -------------------------------------------------- #
        products = self.api.root.add_resource("products")
        self._add_method(
            products,
            "GET",
            products_i,
            operation_name="listProducts",
            request_parameters={"method.request.querystring.maxAnnualFee": False},
        )
        self._add_method(
            products.add_resource("{productId}"),
            "GET",
            products_i,
            operation_name="getProduct",
        )

        # ---- /cards ----------------------------------------------------- #
        cards = self.api.root.add_resource("cards")
        # POST /cards (request a new card)
        self._add_method(cards, "POST", cards_i, operation_name="requestCard")
        # GET /cards?customerId=... (list a customer's card requests)
        self._add_method(
            cards,
            "GET",
            cards_i,
            operation_name="listCustomerCards",
            request_parameters={"method.request.querystring.customerId": False},
        )
        self._add_method(
            cards.add_resource("{cardId}"), "GET", cards_i, operation_name="getCard"
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
            description="Airline self-service API key (API Gateway + AgentCore).",
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
            "AirlineApiKey",
            api_key_name="airline-selfservice-api-key",
            value=key_value,
        )
        self.usage_plan = self.api.add_usage_plan(
            "AirlineUsagePlan", name="airline-selfservice-usage-plan"
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
