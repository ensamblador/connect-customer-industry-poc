"""
Telco new-line requests Lambda handler.

Backs the /lines endpoints of the telco self-service REST API:

    POST /lines                         -> request a new line for a customer
    GET  /lines?customerId=cust-...     -> list a customer's line requests
    GET  /lines/{lineId}                -> a single line request's details

Reads/writes the DynamoDB lines table (env LINES_TABLE); the per-customer
listing uses the GSI in env LINES_CUSTOMER_INDEX. Line ids are generated
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

_TABLE_NAME = os.environ["LINES_TABLE"]
_CUSTOMER_INDEX = os.environ.get("LINES_CUSTOMER_INDEX", "customerId-index")
_dynamodb = boto3.resource("dynamodb")
_table = _dynamodb.Table(_TABLE_NAME)

_AREA_CODE_RE = re.compile(r"^\d{3}$")


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


def _new_line(event) -> dict:
    try:
        payload = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"message": "request body must be valid JSON"})

    customer_id = payload.get("customerId")
    plan_id = payload.get("planId")
    if not customer_id or not plan_id:
        return _response(400, {"message": "customerId and planId are required"})

    area_code = payload.get("areaCode")
    if area_code is not None and not _AREA_CODE_RE.match(str(area_code)):
        return _response(400, {"message": "areaCode must be a 3-digit string"})

    line = {
        "lineId": f"line-{uuid.uuid4().hex[:8]}",
        "customerId": customer_id,
        "planId": plan_id,
        "status": "requested",
        "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if area_code is not None:
        line["areaCode"] = str(area_code)
    if payload.get("notes"):
        line["notes"] = payload["notes"]
    _table.put_item(Item=line)
    return _response(201, line)


def handler(event, _context):
    """API Gateway (REST, proxy) entry point."""
    method = event.get("httpMethod", "GET")
    path_params = event.get("pathParameters") or {}
    query_params = event.get("queryStringParameters") or {}
    line_id = path_params.get("lineId")

    # POST /lines  -> request a new line
    if method == "POST":
        return _new_line(event)

    # GET /lines/{lineId}
    if line_id:
        result = _table.get_item(Key={"lineId": line_id})
        item = result.get("Item")
        if not item:
            return _response(404, {"message": f"line {line_id} not found"})
        return _response(200, item)

    # GET /lines?customerId=...
    customer_id = query_params.get("customerId")
    if not customer_id:
        return _response(400, {"message": "customerId query parameter is required"})
    result = _table.query(
        IndexName=_CUSTOMER_INDEX,
        KeyConditionExpression=Key("customerId").eq(customer_id),
    )
    items = result.get("Items", [])
    return _response(200, {"customerId": customer_id, "lines": items, "count": len(items)})
