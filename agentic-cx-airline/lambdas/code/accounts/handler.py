"""
Airline accounts Lambda handler.

Backs the /accounts endpoints of the airline self-service REST API:

    GET /accounts/{accountId}            -> account profile
    GET /accounts/{accountId}/flights    -> list of flights associated with account
    GET /accounts?phoneNumber=+1...      -> account lookup by phone number
    GET /accounts/by-email?email=...     -> account lookup by email

Reads from the DynamoDB accounts table (env ACCOUNTS_TABLE); the phone-number
lookup uses the GSI in env ACCOUNTS_PHONE_INDEX and the email lookup uses the
GSI in env ACCOUNTS_EMAIL_INDEX. Read-only; no PII is logged.
"""

import json
import os
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

_TABLE_NAME = os.environ["ACCOUNTS_TABLE"]
_PHONE_INDEX = os.environ.get("ACCOUNTS_PHONE_INDEX", "phoneNumber-index")
_EMAIL_INDEX = os.environ.get("ACCOUNTS_EMAIL_INDEX", "email-index")
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


def handler(event, _context):
    """API Gateway (REST, proxy) entry point."""
    path_params = event.get("pathParameters") or {}
    query_params = event.get("queryStringParameters") or {}
    resource = event.get("resource", "")
    account_id = path_params.get("accountId")

    # GET /accounts/by-email?email=...  -> look up by email via the GSI
    if resource.endswith("/by-email"):
        email = query_params.get("email")
        if not email:
            return _response(400, {"message": "email query parameter is required"})
        result = _table.query(
            IndexName=_EMAIL_INDEX,
            KeyConditionExpression=Key("email").eq(email),
        )
        items = result.get("Items", [])
        if not items:
            return _response(404, {"message": f"no account for email {email}"})
        return _response(200, items[0])

    # GET /accounts?phoneNumber=...  -> look up by phone via the GSI
    if account_id is None:
        phone = query_params.get("phoneNumber")
        if not phone:
            return _response(400, {"message": "phoneNumber query parameter is required"})
        result = _table.query(
            IndexName=_PHONE_INDEX,
            KeyConditionExpression=Key("phoneNumber").eq(phone),
        )
        items = result.get("Items", [])
        if not items:
            return _response(404, {"message": f"no account for phone {phone}"})
        return _response(200, items[0])

    # GET /accounts/{accountId}[/flights]
    result = _table.get_item(Key={"accountId": account_id})
    item = result.get("Item")
    if not item:
        return _response(404, {"message": f"account {account_id} not found"})

    if resource.endswith("/flights"):
        return _response(
            200,
            {
                "accountId": account_id,
                "flights": item.get("flights", []),
                "membershipTier": item.get("membershipTier", "classic"),
                "miles": item.get("miles", 0),
            },
        )

    return _response(200, item)
