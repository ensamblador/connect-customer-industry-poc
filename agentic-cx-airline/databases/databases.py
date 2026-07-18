"""
databases/databases.py — DynamoDB tables for the airline self-service backend.

Following the project convention, ALL DynamoDB tables for the project live in
this single `Tables` construct so the stack composes them in one place.

Three tables back the API:

  * accounts  (PK accountId,  GSI phoneNumber-index)  — customer accounts;
                                                        lookup by phone number
  * products  (PK productId)                          — airline product catalog
  * cards     (PK cardId,     GSI customerId-index)   — card / product requests;
                                                        lookup by customer

Sample data is loaded at deploy time with the AwsCustomResource +
DynamoDB BatchWriteItem technique (see databases/data/*.json), modeled on the
aws-samples generative-ai-ml-latam-samples reference. The JSON files are in
DynamoDB's native attribute-value format (e.g. {"S": "..."}, {"N": "..."}).

All tables are on-demand (PAY_PER_REQUEST) and DESTROY-on-delete because this
is a disposable demo stack. For production, switch removal_policy to RETAIN.
"""

from __future__ import annotations

import json
import os

from aws_cdk import RemovalPolicy
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import custom_resources as cr
from constructs import Construct

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

_TABLE_CONFIG = dict(
    billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
    removal_policy=RemovalPolicy.DESTROY,
)


class Tables(Construct):
    """All DynamoDB tables for the airline-cx project (+ sample data)."""

    PHONE_INDEX_NAME = "phoneNumber-index"
    EMAIL_INDEX_NAME = "email-index"
    CUSTOMER_INDEX_NAME = "customerId-index"

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        accounts_table_name: str,
        products_table_name: str,
        cards_table_name: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # accounts — PK accountId; GSI to look an account up by phone number.
        self.accounts = dynamodb.Table(
            self,
            "AccountsTable",
            table_name=accounts_table_name,
            partition_key=dynamodb.Attribute(
                name="accountId", type=dynamodb.AttributeType.STRING
            ),
            **_TABLE_CONFIG,
        )
        self.accounts.add_global_secondary_index(
            index_name=self.PHONE_INDEX_NAME,
            partition_key=dynamodb.Attribute(
                name="phoneNumber", type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )
        self.accounts.add_global_secondary_index(
            index_name=self.EMAIL_INDEX_NAME,
            partition_key=dynamodb.Attribute(
                name="email", type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        # products — PK productId; small catalog, scanned/filtered for listing.
        self.products = dynamodb.Table(
            self,
            "ProductsTable",
            table_name=products_table_name,
            partition_key=dynamodb.Attribute(
                name="productId", type=dynamodb.AttributeType.STRING
            ),
            **_TABLE_CONFIG,
        )

        # cards — PK cardId; GSI to list a customer's card / product requests.
        self.cards = dynamodb.Table(
            self,
            "CardsTable",
            table_name=cards_table_name,
            partition_key=dynamodb.Attribute(
                name="cardId", type=dynamodb.AttributeType.STRING
            ),
            **_TABLE_CONFIG,
        )
        self.cards.add_global_secondary_index(
            index_name=self.CUSTOMER_INDEX_NAME,
            partition_key=dynamodb.Attribute(
                name="customerId", type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        # Load sample data into each table.
        self._load_sample_data("accounts", self.accounts)
        self._load_sample_data("products", self.products)
        self._load_sample_data("cards", self.cards)

    # ------------------------------------------------------------------ #
    def _load_sample_data(self, name: str, table: dynamodb.Table) -> None:
        """
        Seed `table` from databases/data/<name>.json using a single
        BatchWriteItem call via an AwsCustomResource. The JSON is already in
        DynamoDB attribute-value format, so items pass straight through.
        """
        path = os.path.join(_DATA_DIR, f"{name}.json")
        with open(path, encoding="utf-8") as fh:
            sample = json.load(fh)

        items = sample.get("Items", [])
        if not items:
            return

        parameters = {
            "RequestItems": {
                table.table_name: [
                    {"PutRequest": {"Item": item}} for item in items
                ]
            }
        }

        seeder = cr.AwsCustomResource(
            self,
            f"Seed{name.capitalize()}",
            on_update=cr.AwsSdkCall(
                service="dynamodb",
                action="BatchWriteItem",
                parameters=parameters,
                # Re-seed whenever the data content changes (new physical id).
                physical_resource_id=cr.PhysicalResourceId.of(
                    f"seed-{table.table_name}-{len(items)}"
                ),
            ),
            policy=cr.AwsCustomResourcePolicy.from_sdk_calls(
                resources=[table.table_arn]
            ),
        )
        # Don't write before the table exists.
        seeder.node.add_dependency(table)

    # ------------------------------------------------------------------ #
    def get_all_tables(self) -> list[dynamodb.Table]:
        return [self.accounts, self.products, self.cards]
