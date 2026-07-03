"""Unit tests for the dual-protocol products Lambda handler.

The handler serves two callers from one entry point:

  * Amazon Connect "Invoke AWS Lambda function" events (top-level
    ``Details`` key, no ``httpMethod``) -> a view-ready nested-JSON payload
    ``{products, productOptions, count}`` where ``productOptions`` is the
    Dropdown's ``Option[]`` (``{Label, Value}``, ``Value == productId``).
  * API Gateway (REST proxy) events -> the standard ``_response`` envelope
    (``statusCode`` / ``headers`` / JSON ``body``).

These tests lock in both contracts (Requirements 4.1, 4.2).

The module reads ``PRODUCTS_TABLE`` and builds a boto3 DynamoDB table at import
time, so we set the env first, load the handler from its file, then swap the
module-level ``_table`` for an in-memory fake. No AWS calls, no moto needed.

Run with::

    pytest lambdas/code/products/test_handler.py
"""

from __future__ import annotations

import importlib.util
import json
import os
from decimal import Decimal
from pathlib import Path

import pytest

# Satisfy the handler's import-time requirements before loading it.
os.environ.setdefault("PRODUCTS_TABLE", "test-products")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

_HANDLER_PATH = Path(__file__).with_name("handler.py")
_spec = importlib.util.spec_from_file_location("products_handler", _HANDLER_PATH)
products_handler = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(products_handler)


# DynamoDB returns numbers as Decimals; mirror that so the handler's Decimal
# normalization is actually exercised. Field names match the seed data
# (databases/data/products.json): productId, name, annualFee, price, currency.
SEED_PRODUCTS = [
    {
        "productId": "prod-tarjeta-oro",
        "name": "Tarjeta Oro",
        "annualFee": Decimal("50"),
        "price": Decimal("0.00"),
        "currency": "USD",
    },
    {
        "productId": "prod-tarjeta-clasica",
        "name": "Tarjeta Clásica",
        "annualFee": Decimal("0"),
        "price": Decimal("0.00"),
        "currency": "USD",
    },
    {
        "productId": "prod-cuenta-nomina",
        "name": "Cuenta Nómina",
        "annualFee": Decimal("25"),
        "price": Decimal("5.00"),
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
            if item.get("productId") == Key.get("productId"):
                return {"Item": dict(item)}
        return {}


@pytest.fixture(autouse=True)
def fake_table(monkeypatch):
    """Swap the module-level DynamoDB table for an in-memory fake."""
    monkeypatch.setattr(products_handler, "_table", _FakeTable(SEED_PRODUCTS))


def test_connect_event_returns_productoptions_shaped_payload():
    """Connect event -> {products, productOptions, count}; productOptions is Option[].

    Validates: Requirements 4.1, 4.2
    """
    event = {
        "Details": {
            "Parameters": {},
            "ContactData": {"ContactId": "c-123"},
        }
    }

    result = products_handler.handler(event, None)

    # Plain nested dict — NOT the API Gateway envelope.
    assert isinstance(result, dict)
    assert "statusCode" not in result
    assert "body" not in result
    assert set(result.keys()) == {"products", "productOptions", "count"}

    # count agrees with the data and with both lists.
    assert result["count"] == len(SEED_PRODUCTS)
    assert len(result["products"]) == len(SEED_PRODUCTS)
    assert len(result["productOptions"]) == len(SEED_PRODUCTS)

    # productOptions is Option[]: each item is exactly {Label, Value},
    # Value equals the productId, Label is a non-empty (Spanish) string.
    product_ids = {p["productId"] for p in result["products"]}
    for option in result["productOptions"]:
        assert set(option.keys()) == {"Label", "Value"}
        assert option["Value"] in product_ids
        assert isinstance(option["Label"], str) and option["Label"]

    # Every product has a corresponding option (Value covers all productIds).
    assert {o["Value"] for o in result["productOptions"]} == product_ids

    # Decimals are normalized to native JSON numbers (no Decimal leaks).
    assert all(not isinstance(p["annualFee"], Decimal) for p in result["products"])

    # A representative label is human-readable and localized ("/mes").
    by_value = {o["Value"]: o["Label"] for o in result["productOptions"]}
    assert by_value["prod-tarjeta-oro"] == "Tarjeta Oro — cuota anual $50 — $0/mes"


def test_api_gateway_event_returns_unchanged_response_envelope():
    """API Gateway event -> standard _response(200, {products, count}) envelope.

    Validates: Requirements 4.2
    """
    event = {"httpMethod": "GET", "pathParameters": None, "queryStringParameters": None}

    result = products_handler.handler(event, None)

    # Envelope shape preserved.
    assert result["statusCode"] == 200
    assert result["headers"] == {"Content-Type": "application/json"}
    assert isinstance(result["body"], str)

    body = json.loads(result["body"])
    assert set(body.keys()) == {"products", "count"}
    assert body["count"] == len(SEED_PRODUCTS)
    # The API Gateway branch does NOT add productOptions.
    assert "productOptions" not in body


def test_api_gateway_maxannualfee_filter():
    """GET /products?maxAnnualFee=... filters by maximum annual fee."""
    event = {
        "httpMethod": "GET",
        "pathParameters": None,
        "queryStringParameters": {"maxAnnualFee": "25"},
    }

    result = products_handler.handler(event, None)

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    # Only products with annualFee <= 25 remain (clasica=0, nomina=25).
    assert {p["productId"] for p in body["products"]} == {
        "prod-tarjeta-clasica",
        "prod-cuenta-nomina",
    }


def test_api_gateway_single_product_lookup_unchanged():
    """GET /products/{productId} still returns the bare item in the envelope."""
    event = {"httpMethod": "GET", "pathParameters": {"productId": "prod-tarjeta-clasica"}}

    result = products_handler.handler(event, None)

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["productId"] == "prod-tarjeta-clasica"
    assert "productOptions" not in body


def test_api_gateway_unknown_product_returns_404():
    """GET /products/{productId} for a missing product keeps the 404 envelope."""
    event = {"httpMethod": "GET", "pathParameters": {"productId": "prod-missing"}}

    result = products_handler.handler(event, None)

    assert result["statusCode"] == 404
    assert "not found" in json.loads(result["body"])["message"]
