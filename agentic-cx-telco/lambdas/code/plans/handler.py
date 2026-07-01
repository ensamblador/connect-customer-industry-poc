"""
Telco plans Lambda handler.

Backs the /plans endpoints of the telco self-service REST API:

    GET /plans?minGb=25     -> list plans, optionally filtered by minimum GB
    GET /plans/{planId}     -> a single plan's details

Reads from the DynamoDB plans table (env PLANS_TABLE). The catalog is small,
so listing uses Scan and filters minGb in the handler.
"""

import json
import os
from decimal import Decimal

import boto3

_TABLE_NAME = os.environ["PLANS_TABLE"]
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


def _plan_label(plan: dict) -> str:
    """Spanish, human-readable label for a plan, e.g. 'Telco Plus — 25 GB — $45/mes'."""
    parts = [str(plan.get("name") or plan["planId"])]
    if plan.get("dataGb") is not None:
        parts.append(f"{_fmt_number(plan['dataGb'])} GB")
    if plan.get("monthlyPrice") is not None:
        parts.append(f"${_fmt_number(plan['monthlyPrice'])}/mes")
    return " — ".join(parts)


def _handle_connect_event(_event) -> dict:
    """Amazon Connect 'Invoke AWS Lambda function' entry point (ResponseType: JSON).

    Returns nested JSON the contact flow reads under ``$.External``. ``planOptions``
    is pre-shaped as the view Dropdown's ``Option[]`` (``{Label, Value}``) — ``Label``
    is a Spanish, human-readable string and ``Value`` is the ``planId`` — because the
    flow cannot map arrays itself.
    """
    raw_plans = _table.scan().get("Items", [])
    # Sort by data allowance ascending for a predictable, helpful order
    # (mirrors the API Gateway listing).
    raw_plans.sort(key=lambda p: float(p.get("dataGb", 0)))

    # Normalize DynamoDB Decimals to native JSON numbers.
    plans = json.loads(json.dumps(raw_plans, default=_json_default))

    plan_options = [
        {"Label": _plan_label(plan), "Value": plan["planId"]} for plan in plans
    ]

    return {"plans": plans, "planOptions": plan_options, "count": len(plans)}


def handler(event, _context):
    """API Gateway (REST, proxy) entry point."""
    # Amazon Connect "Invoke AWS Lambda function" events carry a top-level
    # "Details" key and no "httpMethod"; serve them the view-ready JSON payload.
    if isinstance(event, dict) and "Details" in event and "httpMethod" not in event:
        return _handle_connect_event(event)

    path_params = event.get("pathParameters") or {}
    query_params = event.get("queryStringParameters") or {}
    plan_id = path_params.get("planId")

    # GET /plans/{planId}
    if plan_id:
        result = _table.get_item(Key={"planId": plan_id})
        item = result.get("Item")
        if not item:
            return _response(404, {"message": f"plan {plan_id} not found"})
        return _response(200, item)

    # GET /plans?minGb=...
    plans = _table.scan().get("Items", [])

    min_gb_raw = query_params.get("minGb")
    if min_gb_raw is not None:
        try:
            min_gb = float(min_gb_raw)
        except ValueError:
            return _response(400, {"message": "minGb must be a number"})
        plans = [p for p in plans if float(p.get("dataGb", 0)) >= min_gb]

    # Sort by data allowance ascending for a predictable, helpful order.
    plans.sort(key=lambda p: float(p.get("dataGb", 0)))
    return _response(200, {"plans": plans, "count": len(plans)})
