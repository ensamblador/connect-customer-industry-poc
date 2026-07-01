"""Unit tests for the dual-protocol plans Lambda handler.

The handler serves two callers from one entry point:

  * Amazon Connect "Invoke AWS Lambda function" events (top-level
    ``Details`` key, no ``httpMethod``) -> a view-ready nested-JSON payload
    ``{plans, planOptions, count}`` where ``planOptions`` is the Dropdown's
    ``Option[]`` (``{Label, Value}``, ``Value == planId``).
  * API Gateway (REST proxy) events -> the standard ``_response`` envelope
    (``statusCode`` / ``headers`` / JSON ``body``).

These tests lock in both contracts (Requirements 3.6, 3.7, 7.1).

The module reads ``PLANS_TABLE`` and builds a boto3 DynamoDB table at import
time, so we set the env first, load the handler from its file, then swap the
module-level ``_table`` for an in-memory fake. No AWS calls, no moto needed.

Run with::

    pytest lambdas/code/plans/test_handler.py
"""

from __future__ import annotations

import importlib.util
import json
import os
from decimal import Decimal
from pathlib import Path

import pytest

# Satisfy the handler's import-time requirements before loading it.
os.environ.setdefault("PLANS_TABLE", "test-plans")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

_HANDLER_PATH = Path(__file__).with_name("handler.py")
_spec = importlib.util.spec_from_file_location("plans_handler", _HANDLER_PATH)
plans_handler = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(plans_handler)


# DynamoDB returns numbers as Decimals; mirror that so the handler's Decimal
# normalization is actually exercised. Field names match the seed data
# (databases/data/plans.json): planId, name, dataGb, monthlyPrice, currency.
SEED_PLANS = [
    {
        "planId": "plan-plus",
        "name": "Telco Plus",
        "dataGb": Decimal("25"),
        "monthlyPrice": Decimal("45.00"),
        "currency": "USD",
    },
    {
        "planId": "plan-basic",
        "name": "Telco Basic",
        "dataGb": Decimal("5"),
        "monthlyPrice": Decimal("25.00"),
        "currency": "USD",
    },
    {
        "planId": "plan-unlimited",
        "name": "Telco Unlimited 5G",
        "dataGb": Decimal("100"),
        "monthlyPrice": Decimal("70.00"),
        "currency": "USD",
    },
]


class _FakeTable:
    """Minimal stand-in for a boto3 DynamoDB Table (scan + get_item)."""

    def __init__(self, items):
        self._items = items

    def scan(self):
        # Return copies so handler-side sorting can't mutate our fixtures.
        return {"Items": [dict(item) for item in self._items]}

    def get_item(self, Key):  # noqa: N803 - boto3 uses this kwarg name
        for item in self._items:
            if item.get("planId") == Key.get("planId"):
                return {"Item": dict(item)}
        return {}


@pytest.fixture(autouse=True)
def fake_table(monkeypatch):
    """Swap the module-level DynamoDB table for an in-memory fake."""
    monkeypatch.setattr(plans_handler, "_table", _FakeTable(SEED_PLANS))


def test_connect_event_returns_planoptions_shaped_payload():
    """Connect event -> {plans, planOptions, count}; planOptions is Option[].

    Validates: Requirements 3.6, 3.7
    """
    event = {
        "Details": {
            "Parameters": {},
            "ContactData": {"ContactId": "c-123"},
        }
    }

    result = plans_handler.handler(event, None)

    # Plain nested dict — NOT the API Gateway envelope.
    assert isinstance(result, dict)
    assert "statusCode" not in result
    assert "body" not in result
    assert set(result.keys()) == {"plans", "planOptions", "count"}

    # count agrees with the data and with both lists.
    assert result["count"] == len(SEED_PLANS)
    assert len(result["plans"]) == len(SEED_PLANS)
    assert len(result["planOptions"]) == len(SEED_PLANS)

    # planOptions is Option[]: each item is exactly {Label, Value},
    # Value equals the planId, Label is a non-empty (Spanish) string.
    plan_ids = {p["planId"] for p in result["plans"]}
    for option in result["planOptions"]:
        assert set(option.keys()) == {"Label", "Value"}
        assert option["Value"] in plan_ids
        assert isinstance(option["Label"], str) and option["Label"]

    # Every plan has a corresponding option (Value covers all planIds).
    assert {o["Value"] for o in result["planOptions"]} == plan_ids

    # Decimals are normalized to native JSON numbers (no Decimal leaks).
    assert all(not isinstance(p["dataGb"], Decimal) for p in result["plans"])

    # A representative label is human-readable and localized ("/mes").
    by_value = {o["Value"]: o["Label"] for o in result["planOptions"]}
    assert by_value["plan-plus"] == "Telco Plus — 25 GB — $45/mes"


def test_api_gateway_event_returns_unchanged_response_envelope():
    """API Gateway event -> standard _response(200, {plans, count}) envelope.

    Validates: Requirements 7.1
    """
    event = {"httpMethod": "GET", "pathParameters": None, "queryStringParameters": None}

    result = plans_handler.handler(event, None)

    # Envelope shape preserved.
    assert result["statusCode"] == 200
    assert result["headers"] == {"Content-Type": "application/json"}
    assert isinstance(result["body"], str)

    body = json.loads(result["body"])
    assert set(body.keys()) == {"plans", "count"}
    assert body["count"] == len(SEED_PLANS)
    # The API Gateway branch does NOT add planOptions.
    assert "planOptions" not in body


def test_api_gateway_single_plan_lookup_unchanged():
    """GET /plans/{planId} still returns the bare item in the envelope."""
    event = {"httpMethod": "GET", "pathParameters": {"planId": "plan-basic"}}

    result = plans_handler.handler(event, None)

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["planId"] == "plan-basic"
    assert "planOptions" not in body


def test_api_gateway_unknown_plan_returns_404():
    """GET /plans/{planId} for a missing plan keeps the 404 envelope."""
    event = {"httpMethod": "GET", "pathParameters": {"planId": "plan-missing"}}

    result = plans_handler.handler(event, None)

    assert result["statusCode"] == 404
    assert "not found" in json.loads(result["body"])["message"]
