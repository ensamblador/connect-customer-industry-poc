"""
Banco products Lambda handler.

Backs the /products endpoints of the banco self-service REST API:

    GET /products?maxAnnualFee=50   -> list products, optionally filtered by
                                       maximum annual fee
    GET /products/{productId}       -> a single product's details

Reads from the DynamoDB products table (env PRODUCTS_TABLE). The catalog is
small, so listing uses Scan and filters maxAnnualFee in the handler.
"""

import json
import os
from decimal import Decimal

import boto3

_TABLE_NAME = os.environ["PRODUCTS_TABLE"]
_dynamodb = boto3.resource("dynamodb")
_table = _dynamodb.Table(_TABLE_NAME)


def _json_default(value):
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    raise TypeError(f"Object of type {type(value)} is not JSON serializable")


def _response(status: int, body) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=_json_default),
    }


def _fmt_number(value) -> str:
    """Render a numeric value without a trailing .0 when it is whole."""
    number = float(value)
    return str(int(number)) if number.is_integer() else str(number)


def _product_label(product: dict) -> str:
    """Spanish, human-readable label for a product,
    e.g. 'Tarjeta Oro — cuota anual $50 — $0/mes'."""
    parts = [str(product.get("name") or product["productId"])]
    if product.get("annualFee") is not None:
        parts.append(f"cuota anual ${_fmt_number(product['annualFee'])}")
    if product.get("price") is not None:
        parts.append(f"${_fmt_number(product['price'])}/mes")
    return " — ".join(parts)


def _handle_connect_event(_event) -> dict:
    """Amazon Connect 'Invoke AWS Lambda function' entry point (ResponseType: JSON).

    Returns nested JSON the contact flow reads under ``$.External``.
    ``productOptions`` is pre-shaped as the view Dropdown's ``Option[]``
    (``{Label, Value}``) — ``Label`` is a Spanish, human-readable string and
    ``Value`` is the ``productId`` — because the flow cannot map arrays itself.
    """
    raw_products = _table.scan().get("Items", [])
    # Sort by annual fee ascending for a predictable, helpful order
    # (mirrors the API Gateway listing).
    raw_products.sort(key=lambda p: float(p.get("annualFee", 0)))

    # Normalize DynamoDB Decimals to native JSON numbers.
    products = json.loads(json.dumps(raw_products, default=_json_default))

    product_options = [
        {"Label": _product_label(product), "Value": product["productId"]}
        for product in products
    ]

    return {
        "products": products,
        "productOptions": product_options,
        "count": len(products),
    }


def handler(event, _context):
    """API Gateway (REST, proxy) entry point."""
    # Amazon Connect "Invoke AWS Lambda function" events carry a top-level
    # "Details" key and no "httpMethod"; serve them the view-ready JSON payload.
    if isinstance(event, dict) and "Details" in event and "httpMethod" not in event:
        return _handle_connect_event(event)

    path_params = event.get("pathParameters") or {}
    query_params = event.get("queryStringParameters") or {}
    product_id = path_params.get("productId")

    # GET /products/{productId}
    if product_id:
        result = _table.get_item(Key={"productId": product_id})
        item = result.get("Item")
        if not item:
            return _response(404, {"message": f"product {product_id} not found"})
        return _response(200, item)

    # GET /products?maxAnnualFee=...
    products = _table.scan().get("Items", [])

    max_annual_fee_raw = query_params.get("maxAnnualFee")
    if max_annual_fee_raw is not None:
        try:
            max_annual_fee = float(max_annual_fee_raw)
        except ValueError:
            return _response(400, {"message": "maxAnnualFee must be a number"})
        products = [
            p for p in products if float(p.get("annualFee", 0)) <= max_annual_fee
        ]

    # Sort by annual fee ascending for a predictable, helpful order.
    products.sort(key=lambda p: float(p.get("annualFee", 0)))
    return _response(200, {"products": products, "count": len(products)})
