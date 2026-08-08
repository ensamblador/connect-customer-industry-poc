"""
Airline reservations Lambda handler.

Backs the /reservations endpoints of the airline self-service REST API:

    POST /reservations                         -> create a new flight reservation
    GET  /reservations?customerId=cust-...     -> list a customer's reservations
    GET  /reservations/{reservationId}         -> a single reservation's details

Reads/writes the DynamoDB reservations table (env RESERVATIONS_TABLE); the
per-customer listing uses the GSI in env RESERVATIONS_CUSTOMER_INDEX.
Reservation ids are generated server-side. A new reservation starts in status
"pending".
"""

import json
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

_TABLE_NAME = os.environ["RESERVATIONS_TABLE"]
_CUSTOMER_INDEX = os.environ.get("RESERVATIONS_CUSTOMER_INDEX", "customerId-index")
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


def _create_reservation(event) -> dict:
    try:
        payload = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"message": "request body must be valid JSON"})

    customer_id = payload.get("customerId")
    flight_id = payload.get("flightId")
    if not customer_id or not flight_id:
        return _response(400, {"message": "customerId and flightId are required"})

    passenger_name = payload.get("passengerName")
    email = payload.get("email")
    date = payload.get("date")
    time = payload.get("time")

    reservation = {
        "reservationId": f"res-{uuid.uuid4().hex[:8]}",
        "customerId": customer_id,
        "flightId": flight_id,
        "status": "pending",
        "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if passenger_name:
        reservation["passengerName"] = passenger_name
    if email:
        reservation["email"] = email
    if date:
        reservation["date"] = date
    if time:
        reservation["time"] = time
    if payload.get("notes"):
        reservation["notes"] = payload["notes"]

    _table.put_item(Item=reservation)
    return _response(201, reservation)


def handler(event, _context):
    """API Gateway (REST, proxy) entry point."""
    method = event.get("httpMethod", "GET")
    path_params = event.get("pathParameters") or {}
    query_params = event.get("queryStringParameters") or {}
    reservation_id = path_params.get("reservationId")

    # POST /reservations  -> create a new reservation
    if method == "POST":
        return _create_reservation(event)

    # GET /reservations/{reservationId}
    if reservation_id:
        result = _table.get_item(Key={"reservationId": reservation_id})
        item = result.get("Item")
        if not item:
            return _response(404, {"message": f"reservation {reservation_id} not found"})
        return _response(200, item)

    # GET /reservations?customerId=...
    customer_id = query_params.get("customerId")
    if not customer_id:
        return _response(400, {"message": "customerId query parameter is required"})
    result = _table.query(
        IndexName=_CUSTOMER_INDEX,
        KeyConditionExpression=Key("customerId").eq(customer_id),
    )
    items = result.get("Items", [])
    return _response(
        200, {"customerId": customer_id, "reservations": items, "count": len(items)}
    )
