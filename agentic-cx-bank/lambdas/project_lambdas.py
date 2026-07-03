"""
lambdas/project_lambdas.py — Lambda functions for the banco self-service backend.

Following the project convention, ALL Lambda functions for the project live
in this single `Lambdas` construct. Handler source lives under
`lambdas/code/<domain>/handler.py`.

  * accounts    -> lambdas/code/accounts/handler.py    (profile, balance, by-phone)
  * products    -> lambdas/code/products/handler.py    (product catalog, filter)
  * cards       -> lambdas/code/cards/handler.py       (request/list/get card requests)
  * ai_session  -> lambdas/code/ai_session/handler.py  (set-customer-session-banco:
                                                        customer lookup + Wisdom
                                                        session UpdateSessionData)

Table names and GSI names are injected via environment variables by the stack
(see set_up_env_vars / grants), so handler code carries no hardcoded names.
"""

from __future__ import annotations

import os

from aws_cdk import Duration
from aws_cdk import aws_lambda as aws_lambda
from constructs import Construct

LAMBDA_CONFIG = dict(
    timeout=Duration.seconds(10),
    memory_size=256,
    runtime=aws_lambda.Runtime.PYTHON_3_12,
    architecture=aws_lambda.Architecture.ARM_64,
    tracing=aws_lambda.Tracing.ACTIVE,
)

_CODE_ROOT = os.path.join(os.path.dirname(__file__), "code")


class Lambdas(Construct):
    """All Lambda functions for the banco-cx project."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.accounts = aws_lambda.Function(
            self,
            "AccountsFunction",
            handler="handler.handler",
            code=aws_lambda.Code.from_asset(os.path.join(_CODE_ROOT, "accounts")),
            **LAMBDA_CONFIG,
        )

        self.products = aws_lambda.Function(
            self,
            "ProductsFunction",
            handler="handler.handler",
            code=aws_lambda.Code.from_asset(os.path.join(_CODE_ROOT, "products")),
            **LAMBDA_CONFIG,
        )

        self.cards = aws_lambda.Function(
            self,
            "CardsFunction",
            handler="handler.handler",
            code=aws_lambda.Code.from_asset(os.path.join(_CODE_ROOT, "cards")),
            **LAMBDA_CONFIG,
        )

        # ai_session — invoked by the set-customer-session-banco flow module:
        # looks the customer up in the accounts table by phone/email and writes
        # the record into the contact's Q in Connect (Wisdom) session.
        self.ai_session = aws_lambda.Function(
            self,
            "AiSessionFunction",
            handler="handler.handler",
            code=aws_lambda.Code.from_asset(os.path.join(_CODE_ROOT, "ai_session")),
            **LAMBDA_CONFIG,
        )

    def get_all_functions(self) -> list[aws_lambda.Function]:
        return [self.accounts, self.products, self.cards, self.ai_session]
