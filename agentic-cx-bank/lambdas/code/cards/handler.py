"""
Banco card requests Lambda handler.

Backs the /cards endpoints of the banco self-service REST API:

    POST /cards                         -> request a new card for a customer
    GET  /cards?customerId=cust-...     -> list a customer's card requests
    GET  /cards/{cardId}                -> a single card request's details

Reads/writes the DynamoDB cards table (env CARDS_TABLE); the per-customer
listing uses the GSI in env CARDS_CUSTOMER_INDEX. Card ids are generated
server-side. A new request starts in status "requested".
"""

import json
import os
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

_TABLE_NAME = os.environ["CARDS_TABLE"]
_CUSTOMER_INDEX = os.environ.get("CARDS_CUSTOMER_INDEX", "customerId-index")
_dynamodb = boto3.resource("dynamodb")
_table = _dynamodb.Table(_TABLE_NAME)

_BRANCH_CODE_RE = re.compile(r"^\d{3}$")


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


def _request_card(event) -> dict:
    try:
        payload = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"message": "request body must be valid JSON"})

    customer_id = payload.get("customerId")
    product_id = payload.get("productId")
    if not customer_id or not product_id:
        return _response(400, {"message": "customerId and productId are required"})

    delivery_branch = payload.get("deliveryBranch")
    if delivery_branch is not None and not _BRANCH_CODE_RE.match(str(delivery_branch)):
        return _response(400, {"message": "deliveryBranch must be a 3-digit string"})

    card = {
        "cardId": f"card-{uuid.uuid4().hex[:8]}",
        "customerId": customer_id,
        "productId": product_id,
        "status": "requested",
        "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if delivery_branch is not None:
        card["deliveryBranch"] = str(delivery_branch)
    if payload.get("notes"):
        card["notes"] = payload["notes"]
    _table.put_item(Item=card)
    return _response(201, card)


def handler(event, _context):
    """API Gateway (REST, proxy) entry point."""
    method = event.get("httpMethod", "GET")
    path_params = event.get("pathParameters") or {}
    query_params = event.get("queryStringParameters") or {}
    card_id = path_params.get("cardId")

    # POST /cards  -> request a new card
    if method == "POST":
        return _request_card(event)

    # GET /cards/{cardId}
    if card_id:
        result = _table.get_item(Key={"cardId": card_id})
        item = result.get("Item")
        if not item:
            return _response(404, {"message": f"card {card_id} not found"})
        return _response(200, item)

    # GET /cards?customerId=...
    customer_id = query_params.get("customerId")
    if not customer_id:
        return _response(400, {"message": "customerId query parameter is required"})
    result = _table.query(
        IndexName=_CUSTOMER_INDEX,
        KeyConditionExpression=Key("customerId").eq(customer_id),
    )
    items = result.get("Items", [])
    return _response(200, {"customerId": customer_id, "cards": items, "count": len(items)})
