"""
tests/unit/test_mcp_template.py — CX-BANCO-MCP (Phase 1) template assertions.

Synthesizes a fresh ``McpStack`` and asserts the Phase-1 data / API / naming
contract against the resulting CloudFormation template:

  * exactly three ``AWS::DynamoDB::Table`` resources, each PAY_PER_REQUEST with a
    single string partition key, and the three expected GSIs across them
    (``phoneNumber-index``, ``email-index`` on accounts; ``customerId-index`` on
    cards) (Requirements 3.1, 3.4);
  * exactly four backend Lambda functions (the ``handler.handler`` functions —
    accounts / products / cards / ai_session — distinct from the AgentCore /
    MCP-integration custom-resource provider Lambdas) (Requirement 4.1);
  * exactly nine API Gateway methods, every one with ``ApiKeyRequired: true``
    (Requirements 4.2, 4.3);
  * exactly one Secrets Manager secret (the single API-key source) and exactly
    one API Gateway usage plan (Requirement 4.3);
  * every published SSM parameter name starts with ``/agentic-cx-bank``
    (Requirements 2.2, 4.8);
  * no ``telco`` substring (any letter casing) survives in the synthesized
    in-scope resource names (Requirements 2.1, 2.3).

``config.HAS_REAL_INSTANCE`` is True (a real alias is configured), so the
instance-bound integrations synthesize too; these assertions target only the
data / API / naming resources listed above and are unaffected by that gating.

Validates: Requirements 2.1, 2.2, 2.3, 3.1, 3.4, 4.1, 4.2, 4.3, 4.8
"""

from __future__ import annotations

import json

import pytest
import aws_cdk as cdk
from aws_cdk.assertions import Template

from agentic_cx_bank.mcp_stack import McpStack

# Backend Lambda handlers are authored as ``handler.handler``; the AgentCore /
# MCP-integration / seed custom-resource provider Lambdas use other handlers
# (framework / index entrypoints), so this string cleanly isolates the four
# banking backend functions from the incidental provider functions.
_BACKEND_HANDLER = "handler.handler"

# GSIs that must exist across the three tables (Requirement 3.4).
_EXPECTED_GSIS = {"phoneNumber-index", "email-index", "customerId-index"}


@pytest.fixture(scope="module")
def template() -> Template:
    """Synthesize a fresh McpStack once and expose its CloudFormation template."""
    app = cdk.App()
    stack = McpStack(app, "CX-BANCO-MCP")
    return Template.from_stack(stack)


# --------------------------------------------------------------------------- #
# Requirements 3.1, 3.4 — three PAY_PER_REQUEST tables, single string PK, GSIs
# --------------------------------------------------------------------------- #

def test_exactly_three_dynamodb_tables(template: Template):
    tables = template.find_resources("AWS::DynamoDB::Table")
    assert len(tables) == 3, f"expected 3 DynamoDB tables, found {len(tables)}"


def test_each_table_is_pay_per_request_with_single_string_pk(template: Template):
    tables = template.find_resources("AWS::DynamoDB::Table")
    for logical_id, table in tables.items():
        props = table["Properties"]
        assert props.get("BillingMode") == "PAY_PER_REQUEST", (
            f"{logical_id} is not PAY_PER_REQUEST"
        )

        key_schema = props["KeySchema"]
        hash_keys = [k for k in key_schema if k["KeyType"] == "HASH"]
        range_keys = [k for k in key_schema if k["KeyType"] == "RANGE"]
        assert len(hash_keys) == 1, f"{logical_id} must have exactly one HASH key"
        assert range_keys == [], f"{logical_id} must have no RANGE key (single PK)"

        pk_name = hash_keys[0]["AttributeName"]
        attr_types = {
            a["AttributeName"]: a["AttributeType"]
            for a in props["AttributeDefinitions"]
        }
        assert attr_types.get(pk_name) == "S", (
            f"{logical_id} partition key {pk_name} must be a string (S)"
        )


def test_expected_gsis_present_across_tables(template: Template):
    tables = template.find_resources("AWS::DynamoDB::Table")
    found_gsis: set[str] = set()
    for table in tables.values():
        for gsi in table["Properties"].get("GlobalSecondaryIndexes", []) or []:
            found_gsis.add(gsi["IndexName"])
    assert _EXPECTED_GSIS <= found_gsis, (
        f"missing GSIs: {_EXPECTED_GSIS - found_gsis}"
    )


# --------------------------------------------------------------------------- #
# Requirement 4.1 — exactly four backend Lambda functions
# --------------------------------------------------------------------------- #

def test_exactly_four_backend_lambdas(template: Template):
    functions = template.find_resources("AWS::Lambda::Function")
    backend = {
        lid: fn
        for lid, fn in functions.items()
        if fn.get("Properties", {}).get("Handler") == _BACKEND_HANDLER
    }
    assert len(backend) == 4, (
        f"expected 4 backend Lambdas (handler={_BACKEND_HANDLER!r}), "
        f"found {len(backend)}: {sorted(backend)}"
    )


# --------------------------------------------------------------------------- #
# Requirements 4.2, 4.3 — nine API methods, every one API-key-required
# --------------------------------------------------------------------------- #

def test_nine_api_methods_all_require_api_key(template: Template):
    methods = template.find_resources("AWS::ApiGateway::Method")
    assert len(methods) == 9, f"expected 9 API methods, found {len(methods)}"
    for logical_id, method in methods.items():
        assert method["Properties"].get("ApiKeyRequired") is True, (
            f"{logical_id} does not require an API key"
        )


# --------------------------------------------------------------------------- #
# Requirement 4.3 — a single Secrets Manager secret + a usage plan
# --------------------------------------------------------------------------- #

def test_single_secret_as_api_key_source(template: Template):
    template.resource_count_is("AWS::SecretsManager::Secret", 1)


def test_usage_plan_present(template: Template):
    template.resource_count_is("AWS::ApiGateway::UsagePlan", 1)


# --------------------------------------------------------------------------- #
# Requirements 2.2, 4.8 — every published SSM parameter is namespaced
# --------------------------------------------------------------------------- #

def test_published_ssm_params_use_bank_namespace(template: Template):
    params = template.find_resources("AWS::SSM::Parameter")
    assert params, "expected at least one published SSM parameter"
    for logical_id, param in params.items():
        name = param["Properties"]["Name"]
        assert isinstance(name, str) and name.startswith("/agentic-cx-bank"), (
            f"{logical_id} publishes SSM name {name!r} outside the "
            "/agentic-cx-bank namespace"
        )


# --------------------------------------------------------------------------- #
# Requirements 2.1, 2.3 — no telco substring survives in in-scope names
# --------------------------------------------------------------------------- #

def test_no_telco_substring_in_resource_names(template: Template):
    """Scan every string-valued name property in the synthesized template and
    assert no ``telco`` token (any casing) survives the re-theme."""
    rendered = json.dumps(template.to_json())
    assert "telco" not in rendered.lower(), (
        "found a 'telco' substring in the synthesized CX-BANCO-MCP template"
    )
